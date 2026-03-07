"""One-shot mode — send a single message and print the response."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import websockets
import websockets.exceptions

from stark_jarvis.config import config
from stark_jarvis.display import print_assistant, print_assistant_end, print_error


async def oneshot(
    message: str,
    access_token: str,
    model_provider: Optional[str] = None,
) -> None:
    """Send a single message, print the streamed response, then exit."""
    server = config.server_url
    if not server:
        print_error("No server configured. Run: jarvis login")
        return

    ws_scheme = "wss" if server.startswith("https") else "ws"
    http_stripped = server.replace("https://", "").replace("http://", "")
    ws_url = f"{ws_scheme}://{http_stripped}/api/v1/ws/chat?token={access_token}"

    provider = model_provider or config.model_provider

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            payload = {
                "message": message,
                "model_provider": provider,
                "voice_enabled": False,
            }
            await ws.send(json.dumps(payload))

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
                except asyncio.TimeoutError:
                    print_error("Response timed out.")
                    break

                if isinstance(raw, bytes):
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")

                if msg_type == "token":
                    content = msg.get("content", "")
                    if content:
                        print_assistant(content)

                elif msg_type == "end":
                    print_assistant_end()
                    break

                elif msg_type == "error":
                    print_error(msg.get("error", "Unknown error"))
                    break

    except websockets.exceptions.InvalidStatusCode as exc:
        if exc.status_code in (401, 403):
            print_error("Authentication expired. Run: jarvis login")
        else:
            print_error(f"Connection failed (HTTP {exc.status_code})")
    except (ConnectionRefusedError, OSError) as exc:
        print_error(f"Cannot reach server: {exc}")
