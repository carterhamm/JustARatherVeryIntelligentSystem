"""WebSocket chat client — streams JARVIS responses with rich terminal UI.

Layout is free-flowing: the banner prints once at the top of the
scrollback, then messages stream downward.  The user can scroll up
through the terminal's scrollback buffer to review history.  The input
prompt renders inline (no bottom-toolbar gap) so it stays compact.
"""

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
    JARVIS_BLUE, JARVIS_ERROR_RED, DIM, BOLD, RESET,
    print_banner,
    run_connecting_animation,
    set_terminal_bg_black,
    reset_terminal_bg,
    clear_screen,
    show_cursor,
    print_user_message,
    print_assistant,
    print_assistant_end,
    print_error,
    print_system_centered,
    print_thinking,
    clear_thinking,
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
            # Check for immediate auth rejection — the server sends an
            # error JSON + close(1008) if the token is invalid/expired.
            try:
                early = await asyncio.wait_for(ws.recv(), timeout=0.5)
                early_msg = json.loads(early) if isinstance(early, str) else {}
                if early_msg.get("type") == "error":
                    # Token expired — re-authenticate and retry
                    stop_anim.set()
                    anim_thread.join(timeout=0.5)
                    reset_terminal_bg()
                    show_cursor()
                    print_error("Session expired. Re-authenticating...")
                    from stark_jarvis.auth import unlock
                    new_access, new_refresh = unlock()
                    config.save_session(new_access, new_refresh)
                    # Retry with fresh token
                    await chat_session(new_access, new_refresh, model_provider)
                    return
            except asyncio.TimeoutError:
                pass  # No immediate error — connection is healthy
            except websockets.exceptions.ConnectionClosed:
                # Server closed before we could read — same as auth failure
                stop_anim.set()
                anim_thread.join(timeout=0.5)
                reset_terminal_bg()
                show_cursor()
                print_error("Session expired. Re-authenticating...")
                from stark_jarvis.auth import unlock
                new_access, new_refresh = unlock()
                config.save_session(new_access, new_refresh)
                await chat_session(new_access, new_refresh, model_provider)
                return

            # Stop connecting animation
            stop_anim.set()
            anim_thread.join(timeout=0.5)

            # ── Print banner once — it scrolls with content ──
            clear_screen()
            print_banner()
            print_system_centered(
                "Connected. Type your message, or /help for commands."
            )
            print()

            while True:
                provider = jarvis_input.provider

                try:
                    user_input = await jarvis_input.async_get_input()
                except (EOFError, KeyboardInterrupt):
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}Goodbye, Sir.{RESET}\n"
                    )
                    sys.stdout.flush()
                    break
                except Exception:
                    continue

                if not user_input:
                    continue

                # ── Handle local commands ──
                cmd = user_input.strip().lower()

                if cmd in ("exit", "quit", "/exit", "/quit"):
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}Goodbye, Sir.{RESET}\n"
                    )
                    sys.stdout.flush()
                    break

                if cmd in ("/model", "/provider"):
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}Current provider: "
                        f"{provider_styled(provider)}{RESET}\n\n"
                    )
                    sys.stdout.flush()
                    continue

                if cmd.startswith("/model ") or cmd.startswith("/provider "):
                    new_provider = cmd.split(None, 1)[1].strip()
                    valid = ("claude", "gemini", "stark_protocol")
                    if new_provider in valid:
                        provider = new_provider
                        jarvis_input.provider = new_provider
                        config.model_provider = new_provider
                        sys.stdout.write(
                            f"\n  {DIM}{JARVIS_BLUE}Switched to "
                            f"{provider_styled(new_provider)}{RESET}\n\n"
                        )
                    else:
                        sys.stdout.write(
                            f"\n    {JARVIS_ERROR_RED}Unknown provider. "
                            f"Options: {', '.join(valid)}{RESET}\n"
                        )
                    sys.stdout.flush()
                    continue

                if cmd == "/new":
                    conversation_id = None
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}New conversation started.{RESET}\n\n"
                    )
                    sys.stdout.flush()
                    continue

                if cmd in ("/help", "/?"):
                    _print_help_to_chat()
                    continue

                # ── Send message ──
                print_user_message(user_input)

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
                        sys.stdout.write(
                            f"\n    {JARVIS_ERROR_RED}Response timed out.{RESET}\n"
                        )
                        sys.stdout.flush()
                        streaming = False
                        break

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
                        pass

                    elif msg_type == "tool_call":
                        tool = msg.get("tool", "")
                        arg = msg.get("tool_arg", "")
                        if tool == "SWITCH_MODEL":
                            valid = ("claude", "gemini", "stark_protocol")
                            if arg in valid:
                                provider = arg
                                jarvis_input.provider = arg
                                config.model_provider = arg

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
                            sys.stdout.write(
                                f"\n    {JARVIS_ERROR_RED}Session expired. "
                                f"Run: jarvis login{RESET}\n"
                            )
                            sys.stdout.flush()
                            return
                        sys.stdout.write(
                            f"\n    {JARVIS_ERROR_RED}{error_text}{RESET}\n"
                        )
                        sys.stdout.flush()
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
        print_error("Connection lost. Your session may have expired. Run: jarvis login")
    except Exception as exc:
        print_error(f"Unexpected: {exc}")
    finally:
        stop_anim.set()
        if anim_thread.is_alive():
            anim_thread.join(timeout=0.5)
        show_cursor()
        reset_terminal_bg()


def _print_help_to_chat() -> None:
    """Print help directly to stdout (within the chat scroll region)."""
    sys.stdout.write(f"""
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
    sys.stdout.flush()
