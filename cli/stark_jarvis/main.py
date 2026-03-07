"""CLI entry point — argument parsing and command dispatch.

Routing rules:
- Any command that needs auth will auto-redirect to login if not configured.
- Unknown commands are treated as one-shot messages.
- Never crashes — all exceptions are caught and shown as friendly errors.
"""

from __future__ import annotations

import sys
import asyncio
import traceback

from stark_jarvis import __version__
from stark_jarvis.display import (
    JARVIS_BLUE, JARVIS_GOLD, JARVIS_RED, DIM, BOLD, RESET,
    print_banner, print_system, print_error, print_success,
)

COMMANDS = {"login", "logout", "purge", "status", "help"}


def main() -> None:
    try:
        _run()
    except KeyboardInterrupt:
        print(f"\n  {DIM}Interrupted.{RESET}")
    except SystemExit:
        raise
    except Exception as exc:
        print_error(f"Unexpected error: {exc}")
        if "--debug" in sys.argv:
            traceback.print_exc()
        sys.exit(1)


def _run() -> None:
    args = sys.argv[1:]

    # Handle --version / --help early
    if "--version" in args or "-V" in args:
        print(f"jarvis {__version__}")
        return
    if "--help" in args or "-h" in args:
        _print_help()
        return

    # Strip --debug flag
    debug = "--debug" in args
    args = [a for a in args if a != "--debug"]

    # Extract --model / -m flag
    model_provider = None
    for flag in ("--model", "-m"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                model_provider = args[idx + 1]
                args = args[:idx] + args[idx + 2:]
            else:
                print_error(f"{flag} requires a value (claude, gemini, stark_protocol)")
                sys.exit(1)
            break

    if model_provider and model_provider not in ("claude", "gemini", "stark_protocol"):
        print_error(f"Unknown provider: {model_provider}. Options: claude, gemini, stark_protocol")
        sys.exit(1)

    # Dispatch commands
    command = args[0] if args else None

    # ── login ──
    if command == "login":
        if len(args) < 2:
            print_error("Usage: jarvis login <server-url> [--email <email>]")
            sys.exit(1)
        server_url = args[1]
        # Ensure URL has a scheme
        if not server_url.startswith("http://") and not server_url.startswith("https://"):
            server_url = f"https://{server_url}"
        email = _extract_flag(args, "--email", "-e")
        from stark_jarvis.auth import login
        login(server_url, email=email)
        return

    # ── logout ──
    if command == "logout":
        from stark_jarvis.auth import logout
        logout()
        return

    # ── purge ──
    if command == "purge":
        from stark_jarvis.config import config, CONFIG_DIR
        config.clear_all()
        import shutil
        if CONFIG_DIR.exists():
            shutil.rmtree(CONFIG_DIR)
        print_success("All JARVIS data removed from this machine.")
        return

    # ── status ──
    if command == "status":
        _show_status()
        return

    # ── help ──
    if command == "help":
        _print_help()
        return

    # ── Everything below needs auth — auto-redirect to login ──
    from stark_jarvis.config import config

    if not config.server_url:
        print_banner()
        print_system("No server configured.\n")
        print(f"  {JARVIS_GOLD}Run:{RESET}  jarvis login <your-server-url>")
        print(f"  {DIM}e.g.  jarvis login https://your-app.up.railway.app{RESET}\n")
        sys.exit(0)

    if not config.has_auth():
        print_banner()
        print_system("Not authenticated.\n")
        print(f"  {JARVIS_GOLD}Run:{RESET}  jarvis login {config.server_url}\n")
        sys.exit(0)

    # Unlock session
    from stark_jarvis.auth import unlock
    access_token, refresh_token = unlock()

    # ── One-shot mode: any non-command args form the message ──
    if args and command not in COMMANDS:
        oneshot_message = " ".join(args)
        from stark_jarvis.oneshot import oneshot
        asyncio.run(oneshot(
            message=oneshot_message,
            access_token=access_token,
            model_provider=model_provider,
        ))
        return

    # ── Interactive mode ──
    print_banner()
    from stark_jarvis.chat import chat_session
    asyncio.run(chat_session(
        access_token=access_token,
        refresh_token=refresh_token,
        model_provider=model_provider,
    ))


def _extract_flag(args: list[str], *flags: str) -> str | None:
    """Extract a flag value from args list."""
    for flag in flags:
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1]
    return None


def _show_status() -> None:
    """Print current connection status."""
    from stark_jarvis.config import config
    from stark_jarvis.display import provider_styled
    print_banner()

    server = config.server_url
    print(f"  {JARVIS_BLUE}Server{RESET}    {server or f'{DIM}Not configured{RESET}'}")

    if config.has_auth():
        print(f"  {JARVIS_BLUE}Auth{RESET}      {DIM}Stored (encrypted){RESET}")
    else:
        print(f"  {JARVIS_BLUE}Auth{RESET}      {DIM}Not logged in{RESET}")

    print(f"  {JARVIS_BLUE}Provider{RESET}  {provider_styled(config.model_provider)}")
    print()


def _print_help() -> None:
    print(f"""
{JARVIS_BLUE}{BOLD}J.A.R.V.I.S. Terminal Client{RESET}  {DIM}v{__version__}{RESET}

{BOLD}Usage{RESET}
  jarvis                              Interactive chat
  jarvis "message"                    One-shot query
  jarvis login <url>                  Connect to a JARVIS server
  jarvis logout                       Clear stored credentials
  jarvis purge                        Remove all data from this machine
  jarvis status                       Show connection info

{BOLD}Options{RESET}
  --model, -m <provider>              claude, gemini, stark_protocol
  --version, -V                       Show version
  --help, -h                          Show this help
  --debug                             Show full error traces

{BOLD}Interactive Shortcuts{RESET}
  Ctrl+T                              Cycle model provider
  Enter                               Send message
  Shift+Enter                         New line
  Ctrl+C                              Exit

{BOLD}Examples{RESET}
  {DIM}# First time setup{RESET}
  jarvis login https://your-app.up.railway.app

  {DIM}# Interactive chat{RESET}
  jarvis

  {DIM}# Quick question{RESET}
  jarvis "What time is it in Tokyo?"

  {DIM}# Use Gemini{RESET}
  jarvis -m gemini "Summarize this paper"
""")


if __name__ == "__main__":
    main()
