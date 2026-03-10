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

import glob
import json
import logging
import os
import plistlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis.mac_mini_agent")

app = FastAPI(title="JARVIS Mac Mini Agent", version="1.1.0")

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


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — no auth required."""
    return {"status": "online", "service": "jarvis-mac-mini-agent", "version": "1.1.0"}


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
