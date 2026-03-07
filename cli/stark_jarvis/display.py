"""Terminal display — JARVIS-themed colours, spinners, formatted output."""

from __future__ import annotations

import shutil
import sys
import threading
import time

# ── JARVIS colour palette (matching web UI) ──────────────────────────────
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

# Provider maps
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

# ── Animation ────────────────────────────────────────────────────────────
_spinner_active = False
_spinner_thread: threading.Thread | None = None
_spinner_provider = ""

_SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]

# ── Geometry ─────────────────────────────────────────────────────────────
_BOX_W = 43  # inner width of banner box

_TITLE = "J.A.R.V.I.S.  Terminal"                  # 22 chars
_SUBTITLE = "Just A Rather Very Intelligent System"  # 37 chars
_STATUS_CONNECTED = "Stark Secure Server \u2014 Connected"  # 31 chars


def _term_size() -> tuple[int, int]:
    ts = shutil.get_terminal_size()
    return ts.columns, ts.lines


def _center(text: str, visible_len: int) -> str:
    cols = _term_size()[0]
    pad = max((cols - visible_len) // 2, 0)
    return " " * pad + text


def _pad(text_len: int, w: int = _BOX_W) -> tuple[int, int]:
    pl = (w - text_len) // 2
    return pl, w - text_len - pl


def provider_styled(provider: str) -> str:
    color = PROVIDER_COLORS.get(provider, JARVIS_BLUE)
    label = PROVIDER_LABELS.get(provider, provider)
    return f"{color}{BOLD}{label}{RESET}"


# ── Terminal control ─────────────────────────────────────────────────────

def set_terminal_bg_black() -> None:
    sys.stdout.write("\x1b]11;rgb:00/00/00\x1b\\")
    sys.stdout.flush()


def reset_terminal_bg() -> None:
    sys.stdout.write("\x1b]111\x1b\\")
    sys.stdout.flush()


def clear_screen() -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def hide_cursor() -> None:
    sys.stdout.write("\x1b[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\x1b[?25h")
    sys.stdout.flush()


# ── Banner ───────────────────────────────────────────────────────────────

def _box_lines(
    status: str = _STATUS_CONNECTED,
    status_color: str = "",
) -> list[str]:
    """Build the banner box as a list of ANSI-colored strings."""
    w = _BOX_W
    B = f"{JARVIS_BLUE}{BOLD}"

    tl, tr = _pad(len(_TITLE))
    sl, sr = _pad(len(_SUBTITLE))
    stl, str_ = _pad(len(status))

    sc = status_color if status_color else f"{DIM}{JARVIS_BLUE}"

    return [
        f"{B}\u2554{'═' * w}\u2557",
        f"\u2551{' ' * w}\u2551",
        f"\u2551{' ' * tl}{_TITLE}{' ' * tr}\u2551",
        f"\u2551{' ' * sl}{DIM}{JARVIS_BLUE}{_SUBTITLE}{RESET}{B}{' ' * sr}\u2551",
        f"\u2551{' ' * w}\u2551",
        f"\u2551{' ' * stl}{sc}{status}{RESET}{B}{' ' * str_}\u2551",
        f"\u2551{' ' * w}\u2551",
        f"\u255a{'═' * w}\u255d{RESET}",
    ]


def print_banner() -> None:
    """Print the connected banner, centered."""
    bv = _BOX_W + 2
    print()
    for line in _box_lines():
        print(_center(line, bv))
    print()


def _banner_line_count() -> int:
    """Lines the banner occupies: 8 box lines + 2 blank = 10."""
    return 10


def run_connecting_animation(
    provider: str,
    stop_event: threading.Event,
) -> None:
    """Show animated connecting status inside the banner box."""
    bv = _BOX_W + 2
    label = PROVIDER_LABELS.get(provider, provider)
    color = PROVIDER_COLORS.get(provider, JARVIS_BLUE)

    i = 0
    while not stop_event.is_set():
        spinner = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
        status = f"{spinner} Connecting [{label}]..."
        box = _box_lines(status=status, status_color=color)

        buf = "\x1b[H\n"
        for line in box:
            buf += _center(line, bv) + "\x1b[K\n"
        buf += "\n"

        sys.stdout.write(buf)
        sys.stdout.flush()
        i += 1
        stop_event.wait(0.12)


def fill_to_bottom(used_lines: int) -> None:
    """Print empty lines to push the cursor near the bottom of the terminal."""
    _, rows = _term_size()
    fill = max(rows - used_lines - 3, 0)
    if fill > 0:
        sys.stdout.write("\n" * fill)
        sys.stdout.flush()


# ── Output functions ─────────────────────────────────────────────────────

def print_system(text: str) -> None:
    print(f"  {DIM}{JARVIS_BLUE}{text}{RESET}")


def print_system_centered(text: str) -> None:
    print(_center(f"{DIM}{JARVIS_BLUE}{text}{RESET}", len(text)))


def print_error(text: str) -> None:
    print(f"\n  {JARVIS_RED}{BOLD}ERROR{RESET} {JARVIS_RED}{text}{RESET}")


def print_success(text: str) -> None:
    print(f"  {JARVIS_GREEN}{text}{RESET}")


def print_assistant(content: str) -> None:
    sys.stdout.write(f"{RESET}{content}")
    sys.stdout.flush()


def print_assistant_end() -> None:
    show_cursor()
    print(f"{RESET}\n")


def print_divider() -> None:
    print(f"  {JARVIS_DIM}{'─' * 50}{RESET}")


# ── Spinner ──────────────────────────────────────────────────────────────

def print_thinking(provider: str = "") -> None:
    global _spinner_active, _spinner_thread, _spinner_provider
    hide_cursor()
    _spinner_active = True
    _spinner_provider = provider
    _spinner_thread = threading.Thread(target=_spin, daemon=True)
    _spinner_thread.start()


def clear_thinking() -> None:
    global _spinner_active, _spinner_thread
    _spinner_active = False
    if _spinner_thread:
        _spinner_thread.join(timeout=1.0)
        _spinner_thread = None
    sys.stdout.write(CLEAR_LINE)
    sys.stdout.flush()


def _spin() -> None:
    i = 0
    while _spinner_active:
        frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
        label = PROVIDER_LABELS.get(_spinner_provider, "")
        color = PROVIDER_COLORS.get(_spinner_provider, JARVIS_BLUE)
        suffix = f" [{label}]" if label else ""
        sys.stdout.write(
            f"{CLEAR_LINE}  {color}{frame}{RESET} {DIM}Processing{suffix}...{RESET}"
        )
        sys.stdout.flush()
        i += 1
        time.sleep(0.1)
