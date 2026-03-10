#!/usr/bin/env python3
"""
Mac Mini Agent Service for J.A.R.V.I.S.

A lightweight FastAPI service that runs on the Mac Mini, allowing JARVIS
(deployed on Railway) to remotely execute system commands:
- Send iMessages via Messages.app
- Run Shortcuts
- System info queries

Protected by Bearer token auth. Intended to sit behind Caddy + Cloudflare tunnel.

Setup:
  1. Copy this script to ~/jarvis-docker/mac_mini_agent.py on the Mac Mini
  2. pip install fastapi uvicorn
  3. Set AGENT_AUTH_TOKEN env var (or edit below)
  4. Run: uvicorn mac_mini_agent:app --host 0.0.0.0 --port 5060
  5. Add Caddy route: 8790 → 5060 with Bearer auth
  6. Add Cloudflare tunnel ingress: agent.malibupoint.dev → http://localhost:8790
  7. Set on Railway: MAC_MINI_AGENT_URL=https://agent.malibupoint.dev
                     MAC_MINI_AGENT_KEY=<your token>

Launchd plist (save as ~/Library/LaunchAgents/dev.malibupoint.jarvis-agent.plist):
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0">
  <dict>
    <key>Label</key>
    <string>dev.malibupoint.jarvis-agent</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/env</string>
      <string>python3</string>
      <string>-m</string>
      <string>uvicorn</string>
      <string>mac_mini_agent:app</string>
      <string>--host</string>
      <string>0.0.0.0</string>
      <string>--port</string>
      <string>5060</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USER/jarvis-docker</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>AGENT_AUTH_TOKEN</key>
      <string>YOUR_TOKEN_HERE</string>
    </dict>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/jarvis-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/jarvis-agent.err</string>
  </dict>
  </plist>
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis.mac_mini_agent")

app = FastAPI(title="JARVIS Mac Mini Agent", version="1.0.0")

AUTH_TOKEN = os.environ.get("AGENT_AUTH_TOKEN", "")


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
    to: str  # Phone number or Apple ID
    text: str
    service: str = "iMessage"  # "iMessage" or "SMS"


class SendMessageResponse(BaseModel):
    success: bool
    message: str
    recipient: str


class RunShortcutRequest(BaseModel):
    name: str  # Shortcut name
    input_text: str = ""


class RunShortcutResponse(BaseModel):
    success: bool
    output: str


class SystemInfoResponse(BaseModel):
    hostname: str
    uptime: str
    cpu_usage: str
    memory: str
    agent_version: str = "1.0.0"


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — no auth required."""
    return {"status": "online", "service": "jarvis-mac-mini-agent", "version": "1.0.0"}


@app.post("/send-imessage", response_model=SendMessageResponse)
async def send_imessage(
    req: SendMessageRequest,
    _: str = Depends(verify_token),
):
    """Send an iMessage or SMS via Messages.app using osascript."""
    recipient = req.to.strip()
    text = req.text.strip()

    if not recipient or not text:
        raise HTTPException(400, "Both 'to' and 'text' are required")

    # Sanitise for AppleScript — escape backslashes and quotes
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
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logger.error("osascript failed: %s", error_msg)

            # Provide helpful error messages
            if "-1743" in error_msg:
                return SendMessageResponse(
                    success=False,
                    message=(
                        "Messages.app automation not authorised. "
                        "Go to System Settings > Privacy & Security > Automation "
                        "and grant this process access to Messages."
                    ),
                    recipient=recipient,
                )
            elif "participant" in error_msg.lower():
                return SendMessageResponse(
                    success=False,
                    message=f"Could not find recipient: {recipient}. Check the phone number or Apple ID.",
                    recipient=recipient,
                )
            else:
                return SendMessageResponse(
                    success=False,
                    message=f"osascript error: {error_msg}",
                    recipient=recipient,
                )

        logger.info("iMessage sent to %s", recipient)
        return SendMessageResponse(
            success=True,
            message="Message sent",
            recipient=recipient,
        )

    except subprocess.TimeoutExpired:
        return SendMessageResponse(
            success=False,
            message="osascript timed out after 15 seconds",
            recipient=recipient,
        )
    except Exception as e:
        logger.exception("Failed to send iMessage")
        return SendMessageResponse(
            success=False,
            message=f"Error: {e}",
            recipient=recipient,
        )


@app.post("/run-shortcut", response_model=RunShortcutResponse)
async def run_shortcut(
    req: RunShortcutRequest,
    _: str = Depends(verify_token),
):
    """Run a macOS Shortcut by name."""
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Shortcut 'name' is required")

    cmd = ["shortcuts", "run", name]
    stdin_data = req.input_text if req.input_text else None

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=stdin_data,
            timeout=30,
        )

        if result.returncode != 0:
            return RunShortcutResponse(
                success=False,
                output=f"Shortcut failed: {result.stderr.strip()}",
            )

        return RunShortcutResponse(
            success=True,
            output=result.stdout.strip() or "Shortcut completed (no output)",
        )

    except subprocess.TimeoutExpired:
        return RunShortcutResponse(success=False, output="Shortcut timed out after 30 seconds")
    except Exception as e:
        return RunShortcutResponse(success=False, output=f"Error: {e}")


@app.get("/system-info", response_model=SystemInfoResponse)
async def system_info(_: str = Depends(verify_token)):
    """Get basic system info from the Mac Mini."""
    hostname = subprocess.getoutput("hostname").strip()
    uptime = subprocess.getoutput("uptime").strip()
    # Get CPU usage
    cpu = subprocess.getoutput(
        "top -l 1 -n 0 | grep 'CPU usage' | head -1"
    ).strip()
    # Get memory
    mem = subprocess.getoutput(
        "vm_stat | head -5"
    ).strip()

    return SystemInfoResponse(
        hostname=hostname,
        uptime=uptime,
        cpu_usage=cpu or "N/A",
        memory=mem or "N/A",
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "5060"))
    uvicorn.run(app, host="0.0.0.0", port=port)
