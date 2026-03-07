"""CLI entry point — argument parsing and command dispatch.

Routing rules:
- `jarvis login` → first-time setup (gate credentials + SHT + account)
- `jarvis` → 4-layer auth then interactive chat
- `jarvis "message"` → 4-layer auth then one-shot
- Unknown commands are treated as one-shot messages.
"""

from __future__ import annotations

import sys
import asyncio
import traceback

from stark_jarvis import __version__
from stark_jarvis.display import (
    JARVIS_BLUE, DIM, BOLD, RESET,
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
        from stark_jarvis.config import DEFAULT_SERVER
        if len(args) >= 2:
            server_url = args[1]
        else:
            server_url = DEFAULT_SERVER
        if not server_url.startswith("http://") and not server_url.startswith("https://"):
            server_url = f"https://{server_url}"
        from stark_jarvis.auth import login
        login(server_url)
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

    # ── Everything below needs auth ──
    from stark_jarvis.config import config

    # Auto-purge if inactive too long
    if config.check_auto_purge():
        print(f"\n  {DIM}Session expired. All JARVIS data purged from this machine.{RESET}")
        print(f"  {JARVIS_BLUE}Run:{RESET}  jarvis login\n")
        sys.exit(0)

    if not config.is_setup():
        print_banner()
        print_system("CLI not configured.\n")
        print(f"  {JARVIS_BLUE}Run:{RESET}  jarvis login")
        print(f"  {DIM}Sets up Stark Secure Server access.{RESET}\n")
        sys.exit(0)

    # Check for existing valid session
    session = config.get_session()
    if session:
        access_token, refresh_token = session
        config.touch_session()
    else:
        # 4-layer unlock
        from stark_jarvis.auth import unlock
        access_token, refresh_token = unlock()

    # ── One-shot mode ──
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

    if config.is_setup():
        print(f"  {JARVIS_BLUE}Auth{RESET}      {DIM}Configured (4-layer){RESET}")
    else:
        print(f"  {JARVIS_BLUE}Auth{RESET}      {DIM}Not configured{RESET}")

    jarvis_user = config.get("jarvis_username")
    if jarvis_user:
        print(f"  {JARVIS_BLUE}User{RESET}      {jarvis_user}")

    print(f"  {JARVIS_BLUE}Provider{RESET}  {provider_styled(config.model_provider)}")
    print()


def _print_help() -> None:
    from stark_jarvis.config import DEFAULT_SERVER
    print(f"""
{JARVIS_BLUE}{BOLD}J.A.R.V.I.S. Terminal Client{RESET}  {DIM}v{__version__}{RESET}
{DIM}Stark Secure Server{RESET}

{BOLD}Usage{RESET}
  jarvis                              Interactive chat (requires auth)
  jarvis "message"                    One-shot query (requires auth)
  jarvis login [url]                  Setup CLI access (defaults to {DEFAULT_SERVER})
  jarvis logout                       Clear stored credentials
  jarvis purge                        Remove all data from this machine
  jarvis status                       Show connection info

{BOLD}Authentication (4 layers){RESET}
  1. Gate Username                    Static CLI access credential
  2. Gate Password                    Static CLI access credential
  3. Secure Handshake Token           Server-verified (same as website)
  4. JARVIS Username                  Your account on the server

{BOLD}Options{RESET}
  --model, -m <provider>              claude, gemini, stark_protocol
  --version, -V                       Show version
  --help, -h                          Show this help
  --debug                             Show full error traces

{BOLD}Interactive Shortcuts{RESET}
  Ctrl+T                              Cycle model provider
  Enter                               Send message
  Ctrl+C (x2)                         Exit

{BOLD}Examples{RESET}
  {DIM}# First time setup{RESET}
  jarvis login

  {DIM}# Interactive chat{RESET}
  jarvis

  {DIM}# Quick question{RESET}
  jarvis "What time is it in Tokyo?"
""")


if __name__ == "__main__":
    main()
