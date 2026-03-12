#!/usr/bin/env python3
"""
Mac Mini Agent Service for J.A.R.V.I.S.

A lightweight FastAPI service that runs on the Mac Mini, allowing JARVIS
(deployed on Railway) to remotely execute system commands:
- Send iMessages via Messages.app
- Get shared locations from Find My
- Run Shortcuts
- System info queries

Protected by Bearer token auth. Sits behind Caddy + Cloudflare tunnel.

After updating, redeploy on the Mac Mini:
  cd ~/jarvis-docker && curl -O <raw-github-url>/backend/scripts/mac_mini_agent.py
  launchctl kickstart -k gui/$(id -u)/dev.malibupoint.jarvis-agent
"""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import logging
import os
import plistlib
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis.mac_mini_agent")

app = FastAPI(title="JARVIS Mac Mini Agent", version="2.0.0")

AUTH_TOKEN = os.environ.get("AGENT_AUTH_TOKEN", "")

# In-memory location cache (updated by Find My reads and /update-location)
_location_cache: dict[str, Any] = {}


# ── Auth ─────────────────────────────────────────────────────────────────

def verify_token(authorization: str = Header(...)) -> str:
    """Verify Bearer token from the Authorization header."""
    if not AUTH_TOKEN:
        raise HTTPException(503, "Agent auth token not configured")
    token = authorization.replace("Bearer ", "").strip()
    if token != AUTH_TOKEN:
        raise HTTPException(401, "Invalid token")
    return token


# ── Models ───────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    to: str
    text: str
    service: str = "iMessage"


class SendMessageResponse(BaseModel):
    success: bool
    message: str
    recipient: str


class RunShortcutRequest(BaseModel):
    name: str
    input_text: str = ""


class RunShortcutResponse(BaseModel):
    success: bool
    output: str


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    name: str = "Mr. Stark"
    accuracy: float = 0.0
    source: str = "shortcut"


class LocationResponse(BaseModel):
    found: bool
    name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    accuracy: float = 0.0
    updated_at: str = ""
    source: str = ""


class ExecRequest(BaseModel):
    command: str
    working_dir: str = ""
    timeout: int = 120
    shell: bool = True


class ExecResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


class ClaudeCodeRequest(BaseModel):
    prompt: str
    working_dir: str = ""
    timeout: int = 600  # Claude Code can take a while
    model: str = ""  # empty = default


class ClaudeCodeResponse(BaseModel):
    success: bool
    output: str
    exit_code: int
    duration_ms: float


# ── Unicode Rich Text (for iMessage bold/italic) ────────────────────────

_BOLD_MAP = {}
_ITALIC_MAP = {}
_BOLD_ITALIC_MAP = {}

def _build_unicode_maps():
    """Build char→Unicode maps for Mathematical Sans-Serif styled characters."""
    # Mathematical Sans-Serif Bold: U+1D5D4 (A) to U+1D607 (z), digits U+1D7EC-U+1D7F5
    bold_upper_start = 0x1D5D4
    bold_lower_start = 0x1D5EE
    bold_digit_start = 0x1D7EC
    # Mathematical Sans-Serif Italic: U+1D608 (A) to U+1D63B (z)
    italic_upper_start = 0x1D608
    italic_lower_start = 0x1D622
    # Mathematical Sans-Serif Bold Italic: U+1D63C (A) to U+1D66F (z)
    bi_upper_start = 0x1D63C
    bi_lower_start = 0x1D656

    for i in range(26):
        upper = chr(ord('A') + i)
        lower = chr(ord('a') + i)
        _BOLD_MAP[upper] = chr(bold_upper_start + i)
        _BOLD_MAP[lower] = chr(bold_lower_start + i)
        _ITALIC_MAP[upper] = chr(italic_upper_start + i)
        _ITALIC_MAP[lower] = chr(italic_lower_start + i)
        _BOLD_ITALIC_MAP[upper] = chr(bi_upper_start + i)
        _BOLD_ITALIC_MAP[lower] = chr(bi_lower_start + i)
    for i in range(10):
        _BOLD_MAP[str(i)] = chr(bold_digit_start + i)

_build_unicode_maps()


def _apply_char_map(text: str, char_map: dict[str, str]) -> str:
    """Convert characters using a Unicode map, leaving unmapped chars as-is."""
    return "".join(char_map.get(c, c) for c in text)


import re as _re

def markdown_to_unicode_rich(text: str) -> str:
    """Convert markdown-style formatting to Unicode styled characters.

    Supports:
      ***bold italic*** or ___bold italic___
      **bold** or __bold__
      *italic* or _italic_
    """
    # Bold italic first (***text*** or ___text___)
    text = _re.sub(
        r'\*\*\*(.+?)\*\*\*|___(.+?)___',
        lambda m: _apply_char_map(m.group(1) or m.group(2), _BOLD_ITALIC_MAP),
        text,
    )
    # Bold (**text** or __text__)
    text = _re.sub(
        r'\*\*(.+?)\*\*|__(.+?)__',
        lambda m: _apply_char_map(m.group(1) or m.group(2), _BOLD_MAP),
        text,
    )
    # Italic (*text* or _text_)
    text = _re.sub(
        r'\*(.+?)\*|_(.+?)_',
        lambda m: _apply_char_map(m.group(1) or m.group(2), _ITALIC_MAP),
        text,
    )
    return text


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — no auth required."""
    return {"status": "online", "service": "jarvis-mac-mini-agent", "version": "2.0.0"}


@app.post("/send-imessage", response_model=SendMessageResponse)
async def send_imessage(
    req: SendMessageRequest,
    _: str = Depends(verify_token),
):
    """Send an iMessage or SMS via Messages.app using osascript."""
    recipient = req.to.strip()
    text = req.text.strip()
    logger.info("send-imessage request: to=%s, length=%d, service=%s", recipient, len(text), req.service)

    if not recipient or not text:
        raise HTTPException(400, "Both 'to' and 'text' are required")

    # Convert markdown bold/italic to Unicode styled characters for iMessage
    text = markdown_to_unicode_rich(text)

    safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
    safe_recipient = recipient.replace("\\", "\\\\").replace('"', '\\"')
    service_name = "iMessage" if req.service == "iMessage" else "SMS"

    applescript = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = {service_name}
        set targetBuddy to participant "{safe_recipient}" of targetService
        send "{safe_text}" to targetBuddy
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True, text=True, timeout=15,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logger.error("osascript send-imessage failed: %s", error_msg)

            if "-1743" in error_msg:
                msg = "Messages.app automation not authorised. Grant access in System Settings > Privacy & Security > Automation."
            elif "participant" in error_msg.lower():
                msg = f"Could not find recipient: {recipient}. Check the phone number or Apple ID."
            else:
                msg = f"osascript error: {error_msg}"
            return SendMessageResponse(success=False, message=msg, recipient=recipient)

        logger.info("iMessage sent successfully to %s (%d chars)", recipient, len(text))
        return SendMessageResponse(success=True, message="Message sent", recipient=recipient)

    except subprocess.TimeoutExpired:
        logger.error("osascript timed out sending to %s", recipient)
        return SendMessageResponse(success=False, message="osascript timed out", recipient=recipient)
    except Exception as e:
        logger.exception("Failed to send iMessage to %s", recipient)
        return SendMessageResponse(success=False, message=f"Error: {e}", recipient=recipient)


@app.get("/get-location", response_model=LocationResponse)
async def get_location(
    name: str = Query("", description="Person name to search for in Find My"),
    _: str = Depends(verify_token),
):
    """Get a shared person's location from Find My cache.

    Tries multiple sources:
    1. Find My cache files (~/Library/Caches/com.apple.findmy.fmipcore/)
    2. In-memory cache (from /update-location or previous Find My reads)
    3. Returns not-found if nothing available
    """
    logger.info("get-location request: name=%r", name)

    # Try Find My cache first
    location = _read_find_my_location(name)
    if location:
        logger.info("Found location via Find My: %s at (%.4f, %.4f)", location["name"], location["latitude"], location["longitude"])
        # Update in-memory cache
        _location_cache[location["name"].lower()] = location
        _location_cache["_latest"] = location
        return LocationResponse(
            found=True,
            name=location["name"],
            latitude=location["latitude"],
            longitude=location["longitude"],
            accuracy=location.get("accuracy", 0.0),
            updated_at=location.get("updated_at", ""),
            source="find_my",
        )

    # Try in-memory cache
    cache_key = name.lower().strip() if name else "_latest"
    cached = _location_cache.get(cache_key) or _location_cache.get("_latest")
    if cached:
        logger.info("Found location in cache: %s at (%.4f, %.4f)", cached.get("name", "?"), cached["latitude"], cached["longitude"])
        return LocationResponse(
            found=True,
            name=cached.get("name", ""),
            latitude=cached["latitude"],
            longitude=cached["longitude"],
            accuracy=cached.get("accuracy", 0.0),
            updated_at=cached.get("updated_at", ""),
            source="cache",
        )

    logger.warning("No location found for %r", name)
    return LocationResponse(found=False)


@app.post("/update-location", response_model=LocationResponse)
async def update_location(
    req: LocationUpdate,
    _: str = Depends(verify_token),
):
    """Update stored location (called by hourly Shortcut or manually)."""
    logger.info("update-location: %s at (%.4f, %.4f) source=%s", req.name, req.latitude, req.longitude, req.source)

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "name": req.name,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "accuracy": req.accuracy,
        "updated_at": now,
        "source": req.source,
    }
    _location_cache[req.name.lower()] = entry
    _location_cache["_latest"] = entry

    return LocationResponse(
        found=True,
        name=req.name,
        latitude=req.latitude,
        longitude=req.longitude,
        accuracy=req.accuracy,
        updated_at=now,
        source=req.source,
    )


@app.post("/run-shortcut", response_model=RunShortcutResponse)
async def run_shortcut(
    req: RunShortcutRequest,
    _: str = Depends(verify_token),
):
    """Run a macOS Shortcut by name."""
    logger.info("run-shortcut request: name=%r", req.name)
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Shortcut 'name' is required")

    try:
        result = subprocess.run(
            ["shortcuts", "run", name],
            capture_output=True, text=True,
            input=req.input_text or None,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("Shortcut %r failed: %s", name, result.stderr.strip())
            return RunShortcutResponse(success=False, output=f"Shortcut failed: {result.stderr.strip()}")

        logger.info("Shortcut %r completed successfully", name)
        return RunShortcutResponse(success=True, output=result.stdout.strip() or "Shortcut completed (no output)")

    except subprocess.TimeoutExpired:
        logger.error("Shortcut %r timed out", name)
        return RunShortcutResponse(success=False, output="Shortcut timed out after 30 seconds")
    except Exception as e:
        logger.exception("Shortcut %r error", name)
        return RunShortcutResponse(success=False, output=f"Error: {e}")


@app.get("/system-info")
async def system_info(_: str = Depends(verify_token)):
    """Get basic system info from the Mac Mini."""
    hostname = subprocess.getoutput("hostname").strip()
    uptime = subprocess.getoutput("uptime").strip()
    cpu = subprocess.getoutput("top -l 1 -n 0 | grep 'CPU usage' | head -1").strip()
    mem = subprocess.getoutput("vm_stat | head -5").strip()
    return {
        "hostname": hostname,
        "uptime": uptime,
        "cpu_usage": cpu or "N/A",
        "memory": mem or "N/A",
        "agent_version": "1.1.0",
        "location_cache_size": len(_location_cache),
    }


# ── Remote Execution ─────────────────────────────────────────────────────

@app.post("/exec", response_model=ExecResponse)
async def remote_exec(
    req: ExecRequest,
    _: str = Depends(verify_token),
):
    """Execute a shell command on the Mac Mini.

    Full remote shell access for JARVIS. Protected by Bearer token auth,
    Caddy proxy, and Cloudflare tunnel.
    """
    command = req.command.strip()
    if not command:
        raise HTTPException(400, "Command is required")

    logger.info("EXEC: command=%r cwd=%r timeout=%d", command, req.working_dir, req.timeout)

    cwd = req.working_dir or str(Path.home())
    if not Path(cwd).exists():
        cwd = str(Path.home())

    t0 = time.monotonic()
    try:
        if req.shell:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=req.timeout,
                cwd=cwd,
                env={**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"},
            )
        else:
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=req.timeout,
                cwd=cwd,
                env={**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"},
            )

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "EXEC_DONE: exit=%d elapsed=%.0fms stdout_len=%d stderr_len=%d",
            result.returncode, elapsed, len(result.stdout), len(result.stderr),
        )

        return ExecResponse(
            success=result.returncode == 0,
            stdout=result.stdout[-50000:],  # cap at 50KB
            stderr=result.stderr[-10000:],
            exit_code=result.returncode,
            duration_ms=round(elapsed, 2),
        )

    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - t0) * 1000
        logger.error("EXEC_TIMEOUT: command=%r after %ds", command, req.timeout)
        return ExecResponse(
            success=False,
            stdout="",
            stderr=f"Command timed out after {req.timeout}s",
            exit_code=-1,
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.exception("EXEC_ERROR: command=%r", command)
        return ExecResponse(
            success=False,
            stdout="",
            stderr=str(e),
            exit_code=-1,
            duration_ms=round(elapsed, 2),
        )


@app.post("/claude-code", response_model=ClaudeCodeResponse)
async def run_claude_code(
    req: ClaudeCodeRequest,
    _: str = Depends(verify_token),
):
    """Run Claude Code (claude CLI) on the Mac Mini with full permissions.

    Executes `claude` with --dangerously-skip-permissions so JARVIS can
    autonomously perform development tasks, system admin, file management, etc.
    """
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Prompt is required")

    # Find claude binary
    claude_bin = shutil.which("claude")
    if not claude_bin:
        # Check common install locations
        for candidate in [
            Path.home() / ".claude" / "local" / "claude",
            Path("/opt/homebrew/bin/claude"),
            Path("/usr/local/bin/claude"),
        ]:
            if candidate.exists():
                claude_bin = str(candidate)
                break

    if not claude_bin:
        return ClaudeCodeResponse(
            success=False,
            output="Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
            exit_code=-1,
            duration_ms=0,
        )

    cwd = req.working_dir or str(Path.home())
    if not Path(cwd).exists():
        cwd = str(Path.home())

    cmd = [claude_bin, "--dangerously-skip-permissions", "-p", prompt, "--output-format", "text"]
    if req.model:
        cmd.extend(["--model", req.model])

    logger.info("CLAUDE_CODE: prompt=%r cwd=%r model=%r", prompt[:200], cwd, req.model or "default")

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=req.timeout,
            cwd=cwd,
            env={**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"},
        )
        elapsed = (time.monotonic() - t0) * 1000

        output = result.stdout.strip() or result.stderr.strip()
        logger.info(
            "CLAUDE_CODE_DONE: exit=%d elapsed=%.0fms output_len=%d",
            result.returncode, elapsed, len(output),
        )

        return ClaudeCodeResponse(
            success=result.returncode == 0,
            output=output[-50000:],  # cap at 50KB
            exit_code=result.returncode,
            duration_ms=round(elapsed, 2),
        )

    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - t0) * 1000
        logger.error("CLAUDE_CODE_TIMEOUT after %ds", req.timeout)
        return ClaudeCodeResponse(
            success=False,
            output=f"Claude Code timed out after {req.timeout}s",
            exit_code=-1,
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.exception("CLAUDE_CODE_ERROR")
        return ClaudeCodeResponse(
            success=False,
            output=str(e),
            exit_code=-1,
            duration_ms=round(elapsed, 2),
        )


@app.get("/screenshot")
async def take_screenshot(
    _: str = Depends(verify_token),
    display: int = Query(1, description="Display number (1 = main)"),
    thumbnail: bool = Query(False, description="Return smaller thumbnail"),
):
    """Capture a screenshot of the Mac Mini's screen.

    Returns the PNG image directly (Content-Type: image/png).
    Use thumbnail=true for a smaller version (~800px wide).
    """
    logger.info("SCREENSHOT: display=%d thumbnail=%s", display, thumbnail)

    tmp_path = f"/tmp/jarvis_screenshot_{int(time.time())}.png"

    try:
        # -x = no sound, -D = specific display
        cmd = ["screencapture", "-x", f"-D{display}", tmp_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0 or not Path(tmp_path).exists():
            logger.error("Screenshot failed: %s", result.stderr.strip())
            raise HTTPException(500, f"Screenshot failed: {result.stderr.strip()}")

        if thumbnail:
            thumb_path = f"/tmp/jarvis_screenshot_thumb_{int(time.time())}.png"
            # Use sips to resize (built into macOS)
            subprocess.run(
                ["sips", "--resampleWidth", "800", tmp_path, "--out", thumb_path],
                capture_output=True, timeout=10,
            )
            if Path(thumb_path).exists():
                img_bytes = Path(thumb_path).read_bytes()
                Path(thumb_path).unlink(missing_ok=True)
            else:
                img_bytes = Path(tmp_path).read_bytes()
        else:
            img_bytes = Path(tmp_path).read_bytes()

        Path(tmp_path).unlink(missing_ok=True)

        logger.info("SCREENSHOT_OK: %d bytes", len(img_bytes))
        return Response(content=img_bytes, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        logger.exception("SCREENSHOT_ERROR")
        raise HTTPException(500, f"Screenshot error: {e}")


@app.get("/screenshot/base64")
async def take_screenshot_base64(
    _: str = Depends(verify_token),
    display: int = Query(1, description="Display number"),
    thumbnail: bool = Query(True, description="Return smaller thumbnail"),
):
    """Capture screenshot and return as base64 JSON (for LLM vision input)."""
    logger.info("SCREENSHOT_B64: display=%d thumbnail=%s", display, thumbnail)

    tmp_path = f"/tmp/jarvis_screenshot_{int(time.time())}.png"

    try:
        cmd = ["screencapture", "-x", f"-D{display}", tmp_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0 or not Path(tmp_path).exists():
            raise HTTPException(500, f"Screenshot failed: {result.stderr.strip()}")

        if thumbnail:
            thumb_path = f"/tmp/jarvis_screenshot_thumb_{int(time.time())}.png"
            subprocess.run(
                ["sips", "--resampleWidth", "1024", tmp_path, "--out", thumb_path],
                capture_output=True, timeout=10,
            )
            if Path(thumb_path).exists():
                img_bytes = Path(thumb_path).read_bytes()
                Path(thumb_path).unlink(missing_ok=True)
            else:
                img_bytes = Path(tmp_path).read_bytes()
        else:
            img_bytes = Path(tmp_path).read_bytes()

        Path(tmp_path).unlink(missing_ok=True)
        b64 = base64.b64encode(img_bytes).decode("ascii")

        return {
            "image_base64": b64,
            "media_type": "image/png",
            "size_bytes": len(img_bytes),
        }

    except HTTPException:
        raise
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        logger.exception("SCREENSHOT_B64_ERROR")
        raise HTTPException(500, f"Screenshot error: {e}")


# ── Find My helpers ──────────────────────────────────────────────────────

def _read_find_my_location(name: str = "") -> Optional[dict[str, Any]]:
    """Read location from Find My cache files.

    Searches ~/Library/Caches/com.apple.findmy.fmipcore/ for People.data
    and Devices.data (plist or JSON format).
    """
    cache_base = Path.home() / "Library" / "Caches" / "com.apple.findmy.fmipcore"

    for filename in ["People.data", "Devices.data"]:
        filepath = cache_base / filename
        if not filepath.exists():
            continue

        try:
            data = _parse_find_my_file(filepath)
            if not isinstance(data, list):
                continue

            for entry in data:
                entry_name = (
                    entry.get("name", "")
                    or f"{entry.get('firstName', '')} {entry.get('lastName', '')}".strip()
                    or entry.get("deviceDisplayName", "")
                    or ""
                )

                loc = entry.get("location") or {}
                lat = loc.get("latitude", 0)
                lng = loc.get("longitude", 0)

                if not lat and not lng:
                    continue

                # If name filter is provided, match it
                if name and name.lower() not in entry_name.lower():
                    continue

                # Convert timestamp if available
                ts = loc.get("timestamp", loc.get("timeStamp", 0))
                updated_at = ""
                if ts:
                    try:
                        # Find My uses milliseconds since epoch
                        if ts > 1e12:
                            ts = ts / 1000
                        updated_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass

                return {
                    "name": entry_name,
                    "latitude": lat,
                    "longitude": lng,
                    "accuracy": loc.get("horizontalAccuracy", 0),
                    "updated_at": updated_at,
                }

        except Exception as e:
            logger.debug("Failed to parse %s: %s", filepath, e)
            continue

    return None


def _parse_find_my_file(filepath: Path) -> Any:
    """Parse a Find My data file (tries plist then JSON)."""
    raw = filepath.read_bytes()

    # Try binary plist first
    try:
        return plistlib.loads(raw)
    except Exception:
        pass

    # Try JSON
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Try text plist
    try:
        return plistlib.loads(raw, fmt=plistlib.FMT_XML)
    except Exception:
        pass

    return None


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "5060"))
    uvicorn.run(app, host="0.0.0.0", port=port)
