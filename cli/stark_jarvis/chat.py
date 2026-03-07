"""WebSocket chat client — streams JARVIS responses with rich terminal UI."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from typing import Optional

import websockets
import websockets.exceptions

from stark_jarvis.config import config
from stark_jarvis.display import (
    JARVIS_BLUE, DIM, BOLD, RESET,
    print_banner,
    run_connecting_animation,
    fill_to_bottom,
    _banner_line_count,
    set_terminal_bg_black,
    reset_terminal_bg,
    clear_screen,
    show_cursor,
    print_assistant,
    print_assistant_end,
    print_error,
    print_system_centered,
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

    # Full-screen: black background + clear
    set_terminal_bg_black()
    clear_screen()

    # Start connecting animation in background thread
    stop_anim = threading.Event()
    anim_thread = threading.Thread(
        target=run_connecting_animation,
        args=(provider, stop_anim),
        daemon=True,
    )
    anim_thread.start()

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_size=10 * 1024 * 1024,
        ) as ws:
            # Stop connecting animation
            stop_anim.set()
            anim_thread.join(timeout=0.5)

            # Redraw with connected banner
            clear_screen()
            print_banner()
            print_system_centered(
                "Connected. Type your message, or /help for commands."
            )
            print()
            fill_to_bottom(_banner_line_count() + 2)

            while True:
                # Sync provider from input UI (user may have cycled with Ctrl+T)
                provider = jarvis_input.provider

                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, jarvis_input.get_input
                    )
                except (EOFError, KeyboardInterrupt):
                    print("\n")
                    print_system_centered("Goodbye, Sir.")
                    break

                if not user_input:
                    continue

                # Handle local commands
                cmd = user_input.strip().lower()
                if cmd in ("exit", "quit", "/exit", "/quit"):
                    print_system_centered("Goodbye, Sir.")
                    break
                if cmd in ("/model", "/provider"):
                    print_system_centered(
                        f"Current provider: {provider_styled(provider)}"
                    )
                    continue
                if cmd.startswith("/model ") or cmd.startswith("/provider "):
                    new_provider = cmd.split(None, 1)[1].strip()
                    valid = ("claude", "gemini", "stark_protocol")
                    if new_provider in valid:
                        provider = new_provider
                        jarvis_input.provider = new_provider
                        config.model_provider = new_provider
                        print_system_centered(
                            f"Switched to {provider_styled(new_provider)}"
                        )
                    else:
                        print_error(
                            f"Unknown provider. Options: {', '.join(valid)}"
                        )
                    continue
                if cmd == "/new":
                    conversation_id = None
                    print_system_centered("New conversation started.")
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
                print_thinking(provider)

                # Stream response
                streaming = True
                first_token = True
                while streaming:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
                    except asyncio.TimeoutError:
                        clear_thinking()
                        show_cursor()
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
                                print(
                                    f"\n  {DIM}Model switched to "
                                    f"{provider_styled(arg)}{RESET}"
                                )

                    elif msg_type == "end":
                        print_assistant_end()
                        streaming = False

                    elif msg_type == "error":
                        clear_thinking()
                        show_cursor()
                        error_text = msg.get("error", "Unknown error")
                        if (
                            "token" in error_text.lower()
                            or "auth" in error_text.lower()
                        ):
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
        print_system_centered("Connection closed.")
    finally:
        # Always stop animation and restore terminal
        stop_anim.set()
        if anim_thread.is_alive():
            anim_thread.join(timeout=0.5)
        show_cursor()
        reset_terminal_bg()


def _print_help() -> None:
    """Print available CLI commands."""
    print(f"""
  {JARVIS_BLUE}{BOLD}Commands{RESET}
  {DIM}{'─' * 44}{RESET}
  {JARVIS_BLUE}/model <provider>{RESET}  Switch provider
  {JARVIS_BLUE}/model{RESET}             Show current provider
  {JARVIS_BLUE}/new{RESET}               Start new conversation
  {JARVIS_BLUE}/help{RESET}              Show this help
  {JARVIS_BLUE}exit{RESET}               Quit

  {JARVIS_BLUE}{BOLD}Shortcuts{RESET}
  {DIM}{'─' * 44}{RESET}
  {JARVIS_BLUE}Ctrl+T{RESET}             Cycle model provider
  {JARVIS_BLUE}Enter{RESET}              Send message
  {JARVIS_BLUE}Ctrl+C (x2){RESET}        Exit

  {JARVIS_BLUE}{BOLD}Providers{RESET}
  {DIM}{'─' * 44}{RESET}
  {provider_styled("claude")}           Anthropic Sonnet (Uplink)
  {provider_styled("gemini")}           Google Flash (Uplink)
  {provider_styled("stark_protocol")}    Self-hosted LLM (Local)
""")
