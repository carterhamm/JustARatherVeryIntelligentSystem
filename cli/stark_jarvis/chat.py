"""WebSocket chat client — streams JARVIS responses with rich terminal UI.

Layout:
  Rows 1-10:  Banner (static)
  Row 11-12:  Status + blank (static)
  Rows 13-N3: Chat area (scroll region — messages appear here)
  Row N-2:    Top separator ─────
  Row N-1:    ❯ input
  Row N:      Bottom separator ────── Claude
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
    JARVIS_BLUE, DIM, BOLD, RESET,
    PROVIDER_COLORS, PROVIDER_LABELS,
    print_banner,
    banner_line_count,
    run_connecting_animation,
    set_terminal_bg_black,
    reset_terminal_bg,
    clear_screen,
    hide_cursor,
    show_cursor,
    move_cursor,
    set_scroll_region,
    reset_scroll_region,
    draw_static_input,
    print_user_message,
    print_assistant,
    print_assistant_end,
    print_error,
    print_system,
    print_system_centered,
    print_thinking,
    clear_thinking,
    print_divider,
    provider_styled,
    _term_size,
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

            # ── Draw the full-screen layout ──
            clear_screen()
            print_banner()
            print_system_centered(
                "Connected. Type your message, or /help for commands."
            )
            print()

            # Calculate layout rows
            cols, rows = _term_size()
            chat_top = banner_line_count() + 3    # first row of chat area
            input_row = rows - 2                   # top separator of input area
            scroll_bottom = input_row - 1          # last row of chat scroll region

            # Draw static input area (below scroll region)
            draw_static_input(input_row, provider)

            # Set scroll region to chat area only
            set_scroll_region(chat_top, scroll_bottom)

            # Track position in chat area
            chat_row = chat_top

            while True:
                # Sync provider from input UI (user may have cycled)
                provider = jarvis_input.provider

                # Move cursor to input area for prompt_toolkit
                move_cursor(input_row)

                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, jarvis_input.get_input
                    )
                except (EOFError, KeyboardInterrupt):
                    move_cursor(chat_row)
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}Goodbye, Sir.{RESET}\n"
                    )
                    sys.stdout.flush()
                    break

                # Redraw static input area (prompt_toolkit erased it on exit)
                draw_static_input(input_row, provider)

                if not user_input:
                    continue

                # ── Handle local commands ──
                cmd = user_input.strip().lower()

                if cmd in ("exit", "quit", "/exit", "/quit"):
                    move_cursor(chat_row)
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}Goodbye, Sir.{RESET}\n"
                    )
                    sys.stdout.flush()
                    break

                if cmd in ("/model", "/provider"):
                    move_cursor(chat_row)
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}Current provider: "
                        f"{provider_styled(provider)}{RESET}\n\n"
                    )
                    sys.stdout.flush()
                    chat_row = min(chat_row + 3, scroll_bottom)
                    continue

                if cmd.startswith("/model ") or cmd.startswith("/provider "):
                    new_provider = cmd.split(None, 1)[1].strip()
                    valid = ("claude", "gemini", "stark_protocol")
                    move_cursor(chat_row)
                    if new_provider in valid:
                        provider = new_provider
                        jarvis_input.provider = new_provider
                        config.model_provider = new_provider
                        draw_static_input(input_row, provider)
                        sys.stdout.write(
                            f"\n  {DIM}{JARVIS_BLUE}Switched to "
                            f"{provider_styled(new_provider)}{RESET}\n\n"
                        )
                    else:
                        sys.stdout.write(
                            f"\n  {JARVIS_BLUE}Unknown provider. "
                            f"Options: {', '.join(valid)}{RESET}\n\n"
                        )
                    sys.stdout.flush()
                    chat_row = min(chat_row + 3, scroll_bottom)
                    continue

                if cmd == "/new":
                    conversation_id = None
                    move_cursor(chat_row)
                    sys.stdout.write(
                        f"\n  {DIM}{JARVIS_BLUE}New conversation started.{RESET}\n\n"
                    )
                    sys.stdout.flush()
                    chat_row = min(chat_row + 3, scroll_bottom)
                    continue

                if cmd in ("/help", "/?"):
                    move_cursor(chat_row)
                    _print_help_to_chat()
                    chat_row = min(chat_row + 20, scroll_bottom)
                    continue

                # ── Send message ──
                # Print user message in chat area
                move_cursor(chat_row)
                print_user_message(user_input)

                # Estimate lines used by user message
                msg_lines = 1
                for line in user_input.split('\n'):
                    msg_lines += max(1, (len(line) + 4 + cols - 1) // cols)
                chat_row = min(chat_row + msg_lines + 2, scroll_bottom)

                # Build and send payload
                payload = {
                    "message": user_input,
                    "model_provider": provider,
                    "voice_enabled": False,
                }
                if conversation_id:
                    payload["conversation_id"] = conversation_id

                await ws.send(json.dumps(payload))

                # Spinner appears in chat area (cursor is there)
                print_thinking(provider)

                # Stream response
                streaming = True
                first_token = True
                response_chars = 0
                response_newlines = 0

                while streaming:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
                    except asyncio.TimeoutError:
                        clear_thinking()
                        show_cursor()
                        sys.stdout.write(
                            f"\n  {JARVIS_BLUE}Response timed out.{RESET}\n\n"
                        )
                        sys.stdout.flush()
                        chat_row = min(chat_row + 3, scroll_bottom)
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
                            response_chars += len(content)
                            response_newlines += content.count('\n')
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
                                draw_static_input(input_row, provider)

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
                                f"\n  {JARVIS_BLUE}Session expired. "
                                f"Run: jarvis login{RESET}\n"
                            )
                            sys.stdout.flush()
                            return
                        sys.stdout.write(
                            f"\n  {JARVIS_BLUE}{error_text}{RESET}\n\n"
                        )
                        sys.stdout.flush()
                        chat_row = min(chat_row + 3, scroll_bottom)
                        streaming = False

                    elif msg_type == "pong":
                        pass

                # Update chat_row after response
                if response_chars > 0:
                    resp_lines = response_newlines + max(
                        1, (response_chars + cols - 1) // cols
                    )
                    chat_row = min(chat_row + resp_lines + 2, scroll_bottom)

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
        stop_anim.set()
        if anim_thread.is_alive():
            anim_thread.join(timeout=0.5)
        reset_scroll_region()
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
