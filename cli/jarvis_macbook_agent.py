#!/usr/bin/env python3
"""
JARVIS MacBook Agent — lightweight read-only monitor.

Runs as a LaunchAgent on Mr. Stark's MacBook. Reports:
1. Focus mode changes (Sleep Focus off = Carter woke up)
2. Missed FaceTime calls (read-only from CallHistory database)
3. Unread iMessages count (read-only from chat.db)

Does NOT give JARVIS any write permissions on the MacBook.
All data is sent to the JARVIS backend via HTTPS POST.

Install:
    python3 -m pip install requests
    # Copy the LaunchAgent plist (see bottom of file)

Usage:
    python3 jarvis_macbook_agent.py

Environment variables:
    JARVIS_API_URL  — backend URL (default: https://app.malibupoint.dev/api/v1)
    JARVIS_SERVICE_KEY — X-Service-Key for authentication
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: python3 -m pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────

JARVIS_API_URL = os.environ.get("JARVIS_API_URL", "https://app.malibupoint.dev/api/v1")
JARVIS_SERVICE_KEY = os.environ.get("JARVIS_SERVICE_KEY", "")

# Polling intervals (seconds)
FOCUS_CHECK_INTERVAL = 30
COMMS_CHECK_INTERVAL = 300  # 5 minutes

# Database paths
CALL_HISTORY_DB = Path.home() / "Library/Application Support/CallHistoryDB/CallHistory.storedata"
MESSAGES_DB = Path.home() / "Library/Messages/chat.db"
DND_ASSERTIONS_DB = Path.home() / "Library/DoNotDisturb/DB/Assertions.json"
DND_MODE_CONFIG = Path.home() / "Library/DoNotDisturb/DB/ModeConfigurations.json"

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("jarvis-macbook-agent")

# ── State ─────────────────────────────────────────────────────────────

_last_focus_state: dict[str, Any] = {}
_last_comms_check: float = 0.0


# ══════════════════════════════════════════════════════════════════════
# JARVIS Backend Communication
# ══════════════════════════════════════════════════════════════════════


def _post_report(event: str, data: dict[str, Any]) -> bool:
    """POST a report to the JARVIS backend. Returns True on success."""
    if not JARVIS_SERVICE_KEY:
        log.warning("JARVIS_SERVICE_KEY not set — skipping report")
        return False

    url = f"{JARVIS_API_URL}/macbook/report"
    headers = {
        "X-Service-Key": JARVIS_SERVICE_KEY,
        "Content-Type": "application/json",
    }
    payload = {"event": event, "data": data}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            log.info("Reported %s to JARVIS", event)
            return True
        else:
            log.warning("JARVIS returned %d for %s: %s", resp.status_code, event, resp.text[:200])
            return False
    except requests.RequestException as exc:
        log.error("Failed to report %s: %s", event, exc)
        return False


# ══════════════════════════════════════════════════════════════════════
# Focus Mode Monitoring
# ══════════════════════════════════════════════════════════════════════


def _read_focus_state() -> dict[str, Any]:
    """Read the current Focus mode state from the DND assertions database.

    Returns a dict with keys like:
        {"sleep": True, "dnd": False, "driving": False, ...}
    or an empty dict if unable to read.
    """
    state: dict[str, Any] = {}

    # Method 1: Read Assertions.json (most reliable on macOS 14+)
    if DND_ASSERTIONS_DB.exists():
        try:
            raw = DND_ASSERTIONS_DB.read_text(encoding="utf-8")
            data = json.loads(raw)

            # The assertions file contains a dict of mode assertions
            # Each active assertion means that focus mode is ON
            store = data.get("data", []) if isinstance(data, dict) else data
            active_modes: set[str] = set()

            if isinstance(store, list):
                for assertion in store:
                    if isinstance(assertion, dict):
                        mode_id = assertion.get("storeAssertionModeIdentifier", "")
                        if "sleep" in mode_id.lower():
                            active_modes.add("sleep")
                        elif "driving" in mode_id.lower():
                            active_modes.add("driving")
                        elif "work" in mode_id.lower():
                            active_modes.add("work")
                        elif "personal" in mode_id.lower():
                            active_modes.add("personal")
                        elif "donotdisturb" in mode_id.lower() or "dnd" in mode_id.lower():
                            active_modes.add("dnd")
                        elif mode_id:
                            active_modes.add("dnd")

            state["sleep"] = "sleep" in active_modes
            state["dnd"] = "dnd" in active_modes
            state["driving"] = "driving" in active_modes
            state["work"] = "work" in active_modes
            state["personal"] = "personal" in active_modes
            state["any_active"] = bool(active_modes)
            state["active_modes"] = sorted(active_modes)
            return state
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            log.debug("Assertions.json read failed: %s", exc)

    # Method 2: Read ModeConfigurations.json
    if DND_MODE_CONFIG.exists():
        try:
            raw = DND_MODE_CONFIG.read_text(encoding="utf-8")
            data = json.loads(raw)
            # Check for active mode configurations
            if isinstance(data, dict):
                for mode_id, config in data.items():
                    if isinstance(config, dict) and config.get("isActive"):
                        mode_name = config.get("name", mode_id).lower()
                        if "sleep" in mode_name:
                            state["sleep"] = True
                        else:
                            state["dnd"] = True
            return state
        except (json.JSONDecodeError, OSError) as exc:
            log.debug("ModeConfigurations.json read failed: %s", exc)

    # Method 3: Fallback — use defaults command
    try:
        result = subprocess.run(
            ["defaults", "read", "com.apple.controlcenter", "NSStatusItem Visible FocusModes"],
            capture_output=True, text=True, timeout=5,
        )
        # This only tells us if the control center icon is visible, not the active mode
        # Not very useful, but better than nothing
        state["focus_icon_visible"] = result.stdout.strip() == "1"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return state


def check_focus_mode() -> None:
    """Check Focus mode and report state changes to JARVIS."""
    global _last_focus_state

    current = _read_focus_state()
    if not current and not _last_focus_state:
        return

    # Detect Sleep Focus transitions
    was_sleep = _last_focus_state.get("sleep", False)
    is_sleep = current.get("sleep", False)

    if was_sleep and not is_sleep:
        # Sleep Focus just turned OFF — Carter woke up!
        log.info("Sleep Focus OFF — Carter woke up")
        _post_report("focus_change", {
            "focus": "sleep",
            "active": False,
            "transition": "sleep_off",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    elif not was_sleep and is_sleep:
        # Sleep Focus just turned ON — Carter going to sleep
        log.info("Sleep Focus ON — Carter going to sleep")
        _post_report("focus_change", {
            "focus": "sleep",
            "active": True,
            "transition": "sleep_on",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Detect other Focus mode changes
    for mode in ("dnd", "driving", "work", "personal"):
        was_active = _last_focus_state.get(mode, False)
        is_active = current.get(mode, False)
        if was_active != is_active:
            log.info("Focus mode '%s' changed: %s -> %s", mode, was_active, is_active)
            _post_report("focus_change", {
                "focus": mode,
                "active": is_active,
                "transition": f"{mode}_{'on' if is_active else 'off'}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    _last_focus_state = current


# ══════════════════════════════════════════════════════════════════════
# Missed Calls (read-only)
# ══════════════════════════════════════════════════════════════════════


def check_missed_calls() -> None:
    """Read-only query of CallHistory database for missed calls in the last hour."""
    if not CALL_HISTORY_DB.exists():
        log.debug("CallHistory database not found at %s", CALL_HISTORY_DB)
        return

    try:
        # Connect read-only
        conn = sqlite3.connect(f"file:{CALL_HISTORY_DB}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Core Data epoch: 2001-01-01 00:00:00 UTC
        # Unix epoch offset: 978307200
        one_hour_ago_core = time.time() - 978307200 - 3600

        cursor.execute(
            """
            SELECT ZADDRESS, ZDURATION,
                   datetime(ZDATE + 978307200, 'unixepoch', 'localtime') as call_time
            FROM ZCALLRECORD
            WHERE ZANSWERED = 0
              AND ZORIGINATED = 0
              AND ZDATE > ?
            ORDER BY ZDATE DESC
            LIMIT 20
            """,
            (one_hour_ago_core,),
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return

        calls = []
        for address, duration, call_time in rows:
            calls.append({
                "caller": address or "Unknown",
                "duration": duration or 0,
                "time": call_time or "",
            })

        if calls:
            log.info("Found %d missed call(s) in the last hour", len(calls))
            _post_report("missed_calls", {"calls": calls, "count": len(calls)})

    except sqlite3.Error as exc:
        log.debug("CallHistory query failed: %s", exc)
    except Exception as exc:
        log.error("Unexpected error checking missed calls: %s", exc)


# ══════════════════════════════════════════════════════════════════════
# Unread Messages (read-only)
# ══════════════════════════════════════════════════════════════════════


def check_unread_messages() -> None:
    """Read-only query of chat.db for unread iMessage count."""
    if not MESSAGES_DB.exists():
        log.debug("Messages database not found at %s", MESSAGES_DB)
        return

    try:
        conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Messages date is in nanoseconds since Core Data epoch
        one_hour_ago_ns = (int(time.time()) - 978307200 - 3600) * 1_000_000_000

        cursor.execute(
            """
            SELECT h.id, COUNT(*) as unread_count
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_read = 0
              AND m.is_from_me = 0
              AND m.date > ?
            GROUP BY h.id
            ORDER BY unread_count DESC
            LIMIT 20
            """,
            (one_hour_ago_ns,),
        )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return

        messages = []
        total = 0
        for contact_id, count in rows:
            messages.append({"contact": contact_id, "count": count})
            total += count

        if messages:
            log.info("Found %d unread message(s) from %d contact(s)", total, len(messages))
            _post_report("unread_messages", {
                "messages": messages,
                "total": total,
            })

    except sqlite3.Error as exc:
        log.debug("Messages query failed: %s", exc)
    except Exception as exc:
        log.error("Unexpected error checking unread messages: %s", exc)


# ══════════════════════════════════════════════════════════════════════
# Main Loop
# ══════════════════════════════════════════════════════════════════════


def main() -> None:
    """Main event loop — polls Focus mode every 30s, comms every 5min."""
    if not JARVIS_SERVICE_KEY:
        log.error(
            "JARVIS_SERVICE_KEY environment variable not set. "
            "Set it to the SERVICE_API_KEY from Railway."
        )
        sys.exit(1)

    log.info("JARVIS MacBook Agent starting")
    log.info("  API URL: %s", JARVIS_API_URL)
    log.info("  Focus check interval: %ds", FOCUS_CHECK_INTERVAL)
    log.info("  Comms check interval: %ds", COMMS_CHECK_INTERVAL)

    global _last_comms_check

    # Initial focus state read (don't report — just establish baseline)
    global _last_focus_state
    _last_focus_state = _read_focus_state()
    log.info("Initial focus state: %s", _last_focus_state)

    # Run comms check immediately on startup
    check_missed_calls()
    check_unread_messages()
    _last_comms_check = time.time()

    while True:
        try:
            # Focus mode — check every 30 seconds
            check_focus_mode()

            # Communications — check every 5 minutes
            now = time.time()
            if now - _last_comms_check >= COMMS_CHECK_INTERVAL:
                check_missed_calls()
                check_unread_messages()
                _last_comms_check = now

            time.sleep(FOCUS_CHECK_INTERVAL)

        except KeyboardInterrupt:
            log.info("Shutting down gracefully")
            break
        except Exception as exc:
            log.exception("Unexpected error in main loop: %s", exc)
            time.sleep(FOCUS_CHECK_INTERVAL)


if __name__ == "__main__":
    main()


# ══════════════════════════════════════════════════════════════════════
# LaunchAgent Installation
# ══════════════════════════════════════════════════════════════════════
#
# Save the following as:
#   ~/Library/LaunchAgents/dev.malibupoint.jarvis-agent.plist
#
# Then load it:
#   launchctl load ~/Library/LaunchAgents/dev.malibupoint.jarvis-agent.plist
#
# To unload:
#   launchctl unload ~/Library/LaunchAgents/dev.malibupoint.jarvis-agent.plist
#
# ──────────────────────────────────────────────────────────────────────
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#   "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0">
# <dict>
#     <key>Label</key>
#     <string>dev.malibupoint.jarvis-agent</string>
#     <key>ProgramArguments</key>
#     <array>
#         <string>/usr/bin/python3</string>
#         <string>/Users/mr.stark/Downloads/JustARatherVeryIntelligentSystem/cli/jarvis_macbook_agent.py</string>
#     </array>
#     <key>EnvironmentVariables</key>
#     <dict>
#         <key>JARVIS_SERVICE_KEY</key>
#         <string>YOUR_SERVICE_API_KEY_HERE</string>
#         <key>JARVIS_API_URL</key>
#         <string>https://app.malibupoint.dev/api/v1</string>
#     </dict>
#     <key>RunAtLoad</key>
#     <true/>
#     <key>KeepAlive</key>
#     <true/>
#     <key>StandardOutPath</key>
#     <string>/tmp/jarvis-agent.log</string>
#     <key>StandardErrorPath</key>
#     <string>/tmp/jarvis-agent.err</string>
#     <key>ThrottleInterval</key>
#     <integer>10</integer>
# </dict>
# </plist>
