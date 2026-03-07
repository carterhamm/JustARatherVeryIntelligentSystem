"""Terminal display — JARVIS-themed colours, spinners, formatted output."""

from __future__ import annotations

import sys
import threading
import time

# ── JARVIS colour palette (matching web UI) ──────────────────────────────
# All UI uses JARVIS blue (#00d4ff) as the primary colour.
JARVIS_BLUE = "\x1b[38;2;0;212;255m"       # #00d4ff — primary cyan
JARVIS_RED = "\x1b[38;2;239;68;68m"        # #ef4444 — errors / stark protocol
JARVIS_GREEN = "\x1b[38;2;52;211;153m"     # #34d399 — success
JARVIS_DIM = "\x1b[38;2;75;85;99m"         # #4b5563 — muted text
CLAUDE_ORANGE = "\x1b[38;2;255;140;0m"     # #ff8c00 — claude provider
GEMINI_BLUE = "\x1b[38;2;59;130;246m"      # #3b82f6 — gemini provider

# Standard ANSI
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"
CLEAR_LINE = "\x1b[2K\r"

# Background accents
BG_DARK = "\x1b[48;2;15;15;20m"            # dark glass background

# Provider colour map
PROVIDER_COLORS = {
    "claude": CLAUDE_ORANGE,
    "gemini": GEMINI_BLUE,
    "stark_protocol": JARVIS_RED,
}

PROVIDER_LABELS = {
    "claude": "Claude",
    "gemini": "Gemini",
    "stark_protocol": "Stark Protocol",
}

# Spinner state
_spinner_active = False
_spinner_thread: threading.Thread | None = None


def provider_styled(provider: str) -> str:
    """Return the provider name styled with its colour."""
    color = PROVIDER_COLORS.get(provider, JARVIS_BLUE)
    label = PROVIDER_LABELS.get(provider, provider)
    return f"{color}{BOLD}{label}{RESET}"


def print_banner() -> None:
    """Print the JARVIS startup banner."""
    print(f"""
{JARVIS_BLUE}{BOLD}  ╔═══════════════════════════════════════════╗
  ║                                           ║
  ║         J.A.R.V.I.S.  Terminal            ║
  ║   {DIM}{JARVIS_BLUE}Just A Rather Very Intelligent System{RESET}{JARVIS_BLUE}{BOLD}  ║
  ║                                           ║
  ║     {DIM}{JARVIS_BLUE}Stark Secure Server — Connected{RESET}{JARVIS_BLUE}{BOLD}      ║
  ║                                           ║
  ╚═══════════════════════════════════════════╝{RESET}
""")


def print_system(text: str) -> None:
    """Print a system/info message."""
    print(f"  {DIM}{JARVIS_BLUE}{text}{RESET}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"\n  {JARVIS_RED}{BOLD}ERROR{RESET} {JARVIS_RED}{text}{RESET}")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"  {JARVIS_GREEN}{text}{RESET}")


def print_assistant(content: str) -> None:
    """Print streaming assistant content (no newline — appends inline)."""
    sys.stdout.write(f"{RESET}{content}")
    sys.stdout.flush()


def print_assistant_end() -> None:
    """Finish an assistant response block."""
    print(f"{RESET}\n")


def print_divider() -> None:
    """Print a subtle divider line."""
    print(f"  {JARVIS_DIM}{'─' * 50}{RESET}")


def print_thinking() -> None:
    """Show a spinner while waiting for the first token."""
    global _spinner_active, _spinner_thread
    _spinner_active = True
    _spinner_thread = threading.Thread(target=_spin, daemon=True)
    _spinner_thread.start()


def clear_thinking() -> None:
    """Stop the thinking spinner."""
    global _spinner_active, _spinner_thread
    _spinner_active = False
    if _spinner_thread:
        _spinner_thread.join(timeout=1.0)
        _spinner_thread = None
    sys.stdout.write(CLEAR_LINE)
    sys.stdout.flush()


def _spin() -> None:
    """Background spinner animation with JARVIS blue."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    while _spinner_active:
        frame = frames[i % len(frames)]
        sys.stdout.write(f"{CLEAR_LINE}  {JARVIS_BLUE}{frame}{RESET} {DIM}Processing...{RESET}")
        sys.stdout.flush()
        i += 1
        time.sleep(0.08)
