"""WebSocket chat client — streams JARVIS responses with rich terminal UI."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Optional

import websockets
import websockets.exceptions

from stark_jarvis.config import config
from stark_jarvis.display import (
    JARVIS_BLUE, JARVIS_GOLD, DIM, BOLD, RESET,
    print_assistant,
    print_assistant_end,
    print_error,
    print_system,
    print_thinking,
    clear_thinking,
    print_divider,
    provider_styled,
)
from stark_jarvis.input_ui import JarvisInput


async def chat_session(
    access_token: str,
    refresh_token: str,
    model_provider: Optional[str] = None,
) -> None:
    """Run an interactive chat session over WebSocket."""
    server = config.server_url
    if not server:
        print_error("No server configured. Run: jarvis login")
        return

    # Build WebSocket URL
    ws_scheme = "wss" if server.startswith("https") else "ws"
    http_stripped = server.replace("https://", "").replace("http://", "")
    ws_url = f"{ws_scheme}://{http_stripped}/api/v1/ws/chat?token={access_token}"

    provider = model_provider or config.model_provider
    conversation_id: Optional[str] = None

    # Set up rich input UI
    jarvis_input = JarvisInput(initial_provider=provider)

    print_system(f"Connecting to J.A.R.V.I.S. [{provider_styled(provider)}]...")

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_size=10 * 1024 * 1024,
        ) as ws:
            print_system("Connected. Type your message, or /help for commands.\n")

            while True:
                # Sync provider from input UI (user may have cycled with Ctrl+T)
                provider = jarvis_input.provider

                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, jarvis_input.get_input
                    )
                except (EOFError, KeyboardInterrupt):
                    print("\n")
                    print_system("Goodbye, Sir.")
                    break

                if not user_input:
                    continue

                # Handle local commands
                cmd = user_input.strip().lower()
                if cmd in ("exit", "quit", "/exit", "/quit"):
                    print_system("Goodbye, Sir.")
                    break
                if cmd in ("/model", "/provider"):
                    print_system(f"Current provider: {provider_styled(provider)}")
                    continue
                if cmd.startswith("/model ") or cmd.startswith("/provider "):
                    new_provider = cmd.split(None, 1)[1].strip()
                    valid = ("claude", "gemini", "stark_protocol")
                    if new_provider in valid:
                        provider = new_provider
                        jarvis_input.provider = new_provider
                        config.model_provider = new_provider
                        print_system(f"Switched to {provider_styled(new_provider)}")
                    else:
                        print_error(f"Unknown provider. Options: {', '.join(valid)}")
                    continue
                if cmd == "/new":
                    conversation_id = None
                    print_system("New conversation started.")
                    print_divider()
                    continue
                if cmd in ("/help", "/?"):
                    _print_help()
                    continue

                # Send message
                payload = {
                    "message": user_input,
                    "model_provider": provider,
                    "voice_enabled": False,
                }
                if conversation_id:
                    payload["conversation_id"] = conversation_id

                await ws.send(json.dumps(payload))
                print_thinking()

                # Stream response
                streaming = True
                first_token = True
                while streaming:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
                    except asyncio.TimeoutError:
                        clear_thinking()
                        print_error("Response timed out.")
                        streaming = False
                        break

                    # Handle binary audio (skip in terminal)
                    if isinstance(raw, bytes):
                        continue

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("type")

                    if msg_type == "start":
                        clear_thinking()
                        if msg.get("conversation_id"):
                            conversation_id = msg["conversation_id"]

                    elif msg_type == "token":
                        content = msg.get("content", "")
                        if content:
                            if first_token:
                                first_token = False
                            print_assistant(content)

                    elif msg_type == "replace":
                        pass  # Terminal already displayed tokens

                    elif msg_type == "tool_call":
                        tool = msg.get("tool", "")
                        arg = msg.get("tool_arg", "")
                        if tool == "SWITCH_MODEL":
                            valid = ("claude", "gemini", "stark_protocol")
                            if arg in valid:
                                provider = arg
                                jarvis_input.provider = arg
                                config.model_provider = arg
                                print(f"\n  {DIM}Model switched to {provider_styled(arg)}{RESET}")

                    elif msg_type == "end":
                        print_assistant_end()
                        streaming = False

                    elif msg_type == "error":
                        clear_thinking()
                        error_text = msg.get("error", "Unknown error")
                        # Handle auth expiry gracefully
                        if "token" in error_text.lower() or "auth" in error_text.lower():
                            print_error("Session expired. Run: jarvis login")
                            return
                        print_error(error_text)
                        streaming = False

                    elif msg_type == "pong":
                        pass

    except websockets.exceptions.InvalidStatusCode as exc:
        if exc.status_code in (401, 403):
            print_error("Authentication expired. Run: jarvis login")
        else:
            print_error(f"Connection failed (HTTP {exc.status_code})")
    except (ConnectionRefusedError, OSError) as exc:
        print_error(f"Cannot reach server: {exc}")
    except websockets.exceptions.ConnectionClosed:
        print_system("\nConnection closed.")


def _print_help() -> None:
    """Print available CLI commands."""
    print(f"""
  {JARVIS_BLUE}{BOLD}Commands{RESET}
  {DIM}{'─' * 44}{RESET}
  {JARVIS_GOLD}/model <provider>{RESET}  Switch provider
  {JARVIS_GOLD}/model{RESET}             Show current provider
  {JARVIS_GOLD}/new{RESET}               Start new conversation
  {JARVIS_GOLD}/help{RESET}              Show this help
  {JARVIS_GOLD}exit{RESET}               Quit

  {JARVIS_BLUE}{BOLD}Shortcuts{RESET}
  {DIM}{'─' * 44}{RESET}
  {JARVIS_GOLD}Ctrl+T{RESET}             Cycle model provider
  {JARVIS_GOLD}Enter{RESET}              Send message
  {JARVIS_GOLD}Shift+Enter{RESET}        New line
  {JARVIS_GOLD}Ctrl+C{RESET}             Exit

  {JARVIS_BLUE}{BOLD}Providers{RESET}
  {DIM}{'─' * 44}{RESET}
  {provider_styled("claude")}           Anthropic Sonnet (Uplink)
  {provider_styled("gemini")}           Google Flash (Uplink)
  {provider_styled("stark_protocol")}    Self-hosted LLM (Local)
""")
