"""
Mac Mini Agent client for JARVIS.

Communicates with the Mac Mini agent service (mac_mini_agent.py) running
on the Mac Mini behind Caddy auth + Cloudflare tunnel. Used for:
- Sending iMessages
- Running Shortcuts
- System info queries
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0


def _get_url() -> str:
    """Get the Mac Mini agent base URL."""
    return settings.MAC_MINI_AGENT_URL.rstrip("/")


def _get_headers() -> dict[str, str]:
    """Get auth headers for the Mac Mini agent."""
    return {"Authorization": f"Bearer {settings.MAC_MINI_AGENT_KEY}"}


def is_configured() -> bool:
    """Check if the Mac Mini agent is configured."""
    return bool(settings.MAC_MINI_AGENT_URL) and bool(settings.MAC_MINI_AGENT_KEY)


async def send_imessage(to: str, text: str, service: str = "iMessage") -> dict[str, Any]:
    """Send an iMessage via the Mac Mini agent.

    Args:
        to: Phone number (E.164) or Apple ID email.
        text: Message text.
        service: "iMessage" or "SMS".

    Returns:
        Dict with success, message, and recipient fields.
    """
    if not is_configured():
        return {
            "success": False,
            "message": "Mac Mini agent not configured (MAC_MINI_AGENT_URL / MAC_MINI_AGENT_KEY missing)",
        }

    url = f"{_get_url()}/send-imessage"
    payload = {"to": to, "text": text, "service": service}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=_get_headers())

            if resp.status_code == 401:
                return {"success": False, "message": "Mac Mini agent auth failed — check MAC_MINI_AGENT_KEY"}
            if resp.status_code == 503:
                return {"success": False, "message": "Mac Mini agent token not configured on the Mini"}

            resp.raise_for_status()
            return resp.json()

    except httpx.ConnectError:
        return {"success": False, "message": "Cannot reach Mac Mini agent — is it running?"}
    except httpx.TimeoutException:
        return {"success": False, "message": "Mac Mini agent request timed out"}
    except Exception as e:
        logger.exception("Mac Mini agent error")
        return {"success": False, "message": f"Mac Mini agent error: {e}"}


async def run_shortcut(name: str, input_text: str = "") -> dict[str, Any]:
    """Run a macOS Shortcut on the Mac Mini.

    Args:
        name: Shortcut name.
        input_text: Optional input text for the shortcut.

    Returns:
        Dict with success and output fields.
    """
    if not is_configured():
        return {"success": False, "output": "Mac Mini agent not configured"}

    url = f"{_get_url()}/run-shortcut"
    payload = {"name": name, "input_text": input_text}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=_get_headers())
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.exception("Mac Mini shortcut error")
        return {"success": False, "output": f"Error: {e}"}


async def get_system_info() -> dict[str, Any]:
    """Get system info from the Mac Mini."""
    if not is_configured():
        return {"error": "Mac Mini agent not configured"}

    url = f"{_get_url()}/system-info"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_get_headers())
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.exception("Mac Mini system info error")
        return {"error": f"Error: {e}"}


async def get_location(name: str = "") -> dict[str, Any]:
    """Get a person's location from Find My on the Mac Mini.

    Args:
        name: Person name to search for (empty = latest known location).

    Returns:
        Dict with found, name, latitude, longitude, accuracy, updated_at, source.
    """
    if not is_configured():
        return {"found": False, "error": "Mac Mini agent not configured"}

    url = f"{_get_url()}/get-location"
    params = {"name": name} if name else {}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_get_headers())

            if resp.status_code == 401:
                return {"found": False, "error": "Mac Mini agent auth failed"}
            resp.raise_for_status()
            return resp.json()

    except httpx.ConnectError:
        return {"found": False, "error": "Cannot reach Mac Mini agent"}
    except httpx.TimeoutException:
        return {"found": False, "error": "Mac Mini agent request timed out"}
    except Exception as e:
        logger.exception("Mac Mini get_location error")
        return {"found": False, "error": f"Error: {e}"}


async def health_check() -> bool:
    """Check if the Mac Mini agent is reachable."""
    if not is_configured():
        return False

    url = f"{_get_url()}/health"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=_get_headers())
            return resp.status_code == 200
    except Exception:
        return False
