"""Terminal display — JARVIS-themed colours, spinners, formatted output."""

from __future__ import annotations

import shutil
import sys
import threading
import time

# ── JARVIS colour palette (matching web UI) ──────────────────────────────
JARVIS_BLUE = "\x1b[38;2;0;212;255m"       # #00d4ff — primary cyan
JARVIS_RED = "\x1b[38;2;239;68;68m"        # #ef4444 — stark protocol
JARVIS_ERROR_RED = "\x1b[38;2;180;40;40m"  # #b42828 — darker toned red for errors
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

# Provider-specific spinner frames (match their CLI tools' style)
_SPINNER_FRAMES_CLAUDE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPINNER_FRAMES_GEMINI = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
_SPINNER_FRAMES_STARK = ["◐", "◓", "◑", "◒"]
_SPINNER_FRAMES_DEFAULT = _SPINNER_FRAMES_STARK

_PROVIDER_SPINNERS = {
    "claude": _SPINNER_FRAMES_CLAUDE,
    "gemini": _SPINNER_FRAMES_GEMINI,
    "stark_protocol": _SPINNER_FRAMES_STARK,
}

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


def move_cursor(row: int, col: int = 1) -> None:
    sys.stdout.write(f"\x1b[{row};{col}H")
    sys.stdout.flush()


def set_scroll_region(top: int, bottom: int) -> None:
    """Set terminal scroll region. Only rows top..bottom will scroll."""
    sys.stdout.write(f"\x1b[{top};{bottom}r")
    sys.stdout.flush()


def reset_scroll_region() -> None:
    """Reset scroll region to full terminal."""
    sys.stdout.write("\x1b[r")
    sys.stdout.flush()


# ── Banner ───────────────────────────────────────────────────────────────

def _box_lines(
    status: str = _STATUS_CONNECTED,
    status_color: str = "",
) -> list[str]:
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
    bv = _BOX_W + 2
    print()
    for line in _box_lines():
        print(_center(line, bv))
    print()


def banner_line_count() -> int:
    """Lines the banner occupies: 8 box lines + 2 blank = 10."""
    return 10


def run_connecting_animation(
    provider: str,
    stop_event: threading.Event,
) -> None:
    bv = _BOX_W + 2
    label = PROVIDER_LABELS.get(provider, provider)
    color = PROVIDER_COLORS.get(provider, JARVIS_BLUE)
    frames = _PROVIDER_SPINNERS.get(provider, _SPINNER_FRAMES_DEFAULT)

    i = 0
    while not stop_event.is_set():
        spinner = frames[i % len(frames)]
        status = f"{spinner} Connecting [{label}]..."
        box = _box_lines(status=status, status_color=color)

        buf = "\x1b[H\n"
        for line in box:
            buf += _center(line, bv) + "\x1b[K\n"
        buf += "\n"

        sys.stdout.write(buf)
        sys.stdout.flush()
        i += 1
        stop_event.wait(0.08)


# ── Static input area (drawn when prompt_toolkit is not active) ──────────

def draw_static_input(row: int, provider: str) -> None:
    """Draw a non-interactive input area at row, row+1, row+2."""
    cols, _ = _term_size()
    label = PROVIDER_LABELS.get(provider, provider)
    color = PROVIDER_COLORS.get(provider, JARVIS_BLUE)
    label_len = len(label) + 1
    line_len = max(cols - label_len, 10)

    # Top separator (full width)
    sys.stdout.write(f"\x1b[{row};1H\x1b[K{JARVIS_DIM}{'─' * cols}{RESET}")
    # Prompt
    sys.stdout.write(f"\x1b[{row + 1};1H\x1b[K  {JARVIS_BLUE}{BOLD}❯ {RESET}")
    # Bottom separator + provider
    sys.stdout.write(
        f"\x1b[{row + 2};1H\x1b[K"
        f"{JARVIS_DIM}{'─' * line_len}{RESET}{color} {label}{RESET}"
    )
    sys.stdout.flush()


# ── Output functions ─────────────────────────────────────────────────────

def print_system(text: str) -> None:
    print(f"  {DIM}{JARVIS_BLUE}{text}{RESET}")


def print_system_centered(text: str) -> None:
    print(_center(f"{DIM}{JARVIS_BLUE}{text}{RESET}", len(text)))


def print_error(text: str) -> None:
    print(f"\n  {JARVIS_ERROR_RED}{BOLD}ERROR{RESET} {JARVIS_ERROR_RED}{text}{RESET}")


def print_success(text: str) -> None:
    print(f"  {JARVIS_GREEN}{text}{RESET}")


def print_user_message(text: str) -> None:
    """Print the user's message right-aligned in JARVIS blue."""
    cols, _ = _term_size()
    pad_r = 4  # right padding
    for line in text.split("\n"):
        visible_len = len(line)
        pad_l = max(cols - visible_len - pad_r, 4)
        sys.stdout.write(f"\n{' ' * pad_l}{JARVIS_BLUE}{line}{RESET}")
    sys.stdout.write(f"{RESET}\n\n")
    sys.stdout.flush()


_PAD_L = "    "  # 4-char left padding for responses
_PAD_R = 4       # right margin
_assistant_col = 0   # current column position in the line
_assistant_word = ""        # word buffer (may contain ANSI codes)
_assistant_word_vlen = 0    # visible length of buffered word

# ── Markdown → ANSI streaming parser ─────────────────────────────────────
# Converts **bold**, *italic*, `code`, ```code blocks```, # headings
# into ANSI terminal formatting during streaming output.

_ANSI_BOLD_ON = "\x1b[1m"
_ANSI_ITALIC_ON = "\x1b[3m"
_ANSI_CODE_COLOR = "\x1b[38;2;140;140;140m"

# Token types for the word wrapper
_TK_CHAR = 0    # visible character (width 1)
_TK_SPACE = 1   # word boundary (width 1)
_TK_NL = 2      # newline
_TK_ANSI = 3    # zero-width ANSI escape

_md_bold: bool = False
_md_italic: bool = False
_md_code: bool = False
_md_code_block: bool = False
_md_heading: bool = False
_md_pending: str = ""
_md_line_start: bool = True


def _md_reset() -> None:
    global _md_bold, _md_italic, _md_code, _md_code_block
    global _md_heading, _md_pending, _md_line_start
    _md_bold = _md_italic = _md_code = _md_code_block = _md_heading = False
    _md_pending = ""
    _md_line_start = True


def _md_style() -> str:
    """ANSI sequence reflecting all currently active markdown styles."""
    s = RESET
    if _md_bold:
        s += _ANSI_BOLD_ON
    if _md_italic:
        s += _ANSI_ITALIC_ON
    if _md_code or _md_code_block:
        s += _ANSI_CODE_COLOR
    if _md_heading:
        s += JARVIS_BLUE + _ANSI_BOLD_ON
    return s


def _ch_tok(ch: str) -> tuple[int, str]:
    if ch == "\n":
        return (_TK_NL, "\n")
    if ch == " ":
        return (_TK_SPACE, " ")
    return (_TK_CHAR, ch)


def _text_toks(text: str) -> list[tuple[int, str]]:
    return [_ch_tok(c) for c in text]


def _md_feed(ch: str) -> list[tuple[int, str]]:
    """Feed one raw character through the markdown parser."""
    global _md_pending, _md_bold, _md_italic, _md_code
    global _md_code_block, _md_heading, _md_line_start

    # ── Code block mode: pass through until \n```\n ──
    if _md_code_block:
        _md_pending += ch
        idx = _md_pending.find("\n```\n")
        if idx != -1:
            before = _md_pending[:idx]
            after = _md_pending[idx + 5:]
            _md_pending = ""
            _md_code_block = False
            _md_line_start = True
            toks = _text_toks(before)
            toks.append((_TK_ANSI, _md_style()))
            toks.append((_TK_NL, "\n"))
            for c in after:
                toks.extend(_md_feed(c))
            return toks
        # Hold back chars that might be part of closing \n```\n
        for sfx in ("\n```", "\n``", "\n`", "\n"):
            if _md_pending.endswith(sfx):
                safe = _md_pending[: -len(sfx)]
                _md_pending = sfx
                return _text_toks(safe)
        safe = _md_pending
        _md_pending = ""
        return _text_toks(safe)

    # ── Inline code mode: pass through until ` ──
    if _md_code:
        if ch == "`":
            _md_code = False
            return [(_TK_ANSI, _md_style())]
        return [_ch_tok(ch)]

    # ── Heading: end on newline ──
    if _md_heading and ch == "\n":
        _md_heading = False
        _md_line_start = True
        return [(_TK_ANSI, _md_style()), (_TK_NL, "\n")]

    # ── Normal mode ──
    _md_pending += ch
    return _md_resolve()


def _md_resolve() -> list[tuple[int, str]]:
    """Resolve the pending buffer into tokens."""
    global _md_pending, _md_bold, _md_italic, _md_code
    global _md_code_block, _md_heading, _md_line_start

    p = _md_pending
    if not p:
        return []

    # ── Backticks ──
    if p in ("`", "``"):
        return []
    if p == "```" and _md_line_start:
        return []
    if p.startswith("```") and _md_line_start:
        if "\n" in p[3:]:
            after_nl = p[p.index("\n", 3) + 1:]
            _md_pending = ""
            _md_code_block = True
            _md_line_start = False
            toks: list[tuple[int, str]] = [(_TK_ANSI, _ANSI_CODE_COLOR)]
            for c in after_nl:
                toks.extend(_md_feed(c))
            return toks
        return []
    if p.startswith("```"):
        _md_pending = ""
        return _text_toks(p)
    if p.startswith("``") and len(p) > 2:
        _md_pending = ""
        return _text_toks(p)
    if p[0] == "`" and len(p) >= 2 and p[1] != "`":
        _md_code = True
        _md_pending = ""
        toks = [(_TK_ANSI, _ANSI_CODE_COLOR)]
        for c in p[1:]:
            toks.append(_ch_tok(c))
        return toks

    # ── Stars ──
    if p == "*":
        return []
    if p == "**":
        _md_bold = not _md_bold
        _md_pending = ""
        return [(_TK_ANSI, _md_style())]
    if p.startswith("**") and len(p) > 2:
        _md_bold = not _md_bold
        rest = p[2:]
        _md_pending = ""
        toks = [(_TK_ANSI, _md_style())]
        for c in rest:
            toks.extend(_md_feed(c))
        return toks
    if p[0] == "*" and len(p) >= 2 and p[1] != "*":
        # Bullet: * followed by space at line start → literal
        if _md_line_start and p[1] == " ":
            _md_pending = ""
            _md_line_start = False
            return _text_toks(p)
        _md_italic = not _md_italic
        rest = p[1:]
        _md_pending = ""
        toks = [(_TK_ANSI, _md_style())]
        for c in rest:
            toks.extend(_md_feed(c))
        return toks

    # ── Headings ──
    if _md_line_start and p[0] == "#":
        if all(c == "#" for c in p):
            return []
        if p[-1] == " " and all(c == "#" for c in p[:-1]):
            _md_heading = True
            _md_pending = ""
            _md_line_start = False
            return [(_TK_ANSI, JARVIS_BLUE + _ANSI_BOLD_ON)]
        if p[-1] not in ("#", " "):
            _md_pending = ""
            _md_line_start = False
            return _text_toks(p)
        return []

    # ── Default: emit literally ──
    _md_pending = ""
    toks = []
    for c in p:
        if c == "\n":
            _md_line_start = True
            if _md_heading:
                _md_heading = False
                toks.append((_TK_ANSI, _md_style()))
            toks.append((_TK_NL, "\n"))
        else:
            if _md_line_start and c not in ("#", "`"):
                _md_line_start = False
            toks.append(_ch_tok(c))
    return toks


def _md_flush() -> list[tuple[int, str]]:
    """Flush pending buffer at end of response."""
    global _md_pending
    toks: list[tuple[int, str]] = []
    if _md_code_block and _md_pending.rstrip("\n").endswith("```"):
        idx = _md_pending.rstrip("\n").rfind("```")
        toks.extend(_text_toks(_md_pending[:idx]))
    elif _md_pending:
        toks.extend(_text_toks(_md_pending))
    _md_pending = ""
    if _md_bold or _md_italic or _md_code or _md_code_block or _md_heading:
        toks.append((_TK_ANSI, RESET))
    return toks


def print_assistant(content: str) -> None:
    global _assistant_col, _assistant_word, _assistant_word_vlen
    cols, _ = _term_size()
    max_col = cols - _PAD_R
    out = ""

    for ch in content:
        for tk_type, tk_str in _md_feed(ch):
            if tk_type == _TK_ANSI:
                # Zero-width: attach to word buffer or output directly
                if _assistant_word_vlen > 0:
                    _assistant_word += tk_str
                else:
                    out += tk_str

            elif tk_type == _TK_NL:
                # Flush word then newline
                if _assistant_word_vlen > 0:
                    if _assistant_col == 0:
                        out += _PAD_L
                        _assistant_col = len(_PAD_L)
                    out += _assistant_word
                    _assistant_col += _assistant_word_vlen
                    _assistant_word = ""
                    _assistant_word_vlen = 0
                out += "\n"
                _assistant_col = 0

            elif tk_type == _TK_SPACE:
                # Flush word then space
                if _assistant_word_vlen > 0:
                    if _assistant_col == 0:
                        out += _PAD_L
                        _assistant_col = len(_PAD_L)
                    if _assistant_col + _assistant_word_vlen > max_col:
                        out += "\n" + _PAD_L
                        _assistant_col = len(_PAD_L)
                    out += _assistant_word
                    _assistant_col += _assistant_word_vlen
                    _assistant_word = ""
                    _assistant_word_vlen = 0
                if _assistant_col == 0:
                    out += _PAD_L
                    _assistant_col = len(_PAD_L)
                if _assistant_col < max_col:
                    out += " "
                    _assistant_col += 1

            else:  # _TK_CHAR
                _assistant_word += tk_str
                _assistant_word_vlen += 1

    # Flush remaining word (more tokens may arrive in next call)
    if _assistant_word_vlen > 0:
        if _assistant_col == 0:
            out += _PAD_L
            _assistant_col = len(_PAD_L)
        if _assistant_col + _assistant_word_vlen > max_col:
            out += "\n" + _PAD_L
            _assistant_col = len(_PAD_L)
        out += _assistant_word
        _assistant_col += _assistant_word_vlen
        _assistant_word = ""
        _assistant_word_vlen = 0

    sys.stdout.write(out)
    sys.stdout.flush()


def print_assistant_end() -> None:
    global _assistant_col, _assistant_word, _assistant_word_vlen
    # Flush any pending markdown
    for tk_type, tk_str in _md_flush():
        sys.stdout.write(tk_str)
    _assistant_col = 0
    _assistant_word = ""
    _assistant_word_vlen = 0
    _md_reset()
    show_cursor()
    sys.stdout.write(f"{RESET}\n")
    sys.stdout.flush()


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
    frames = _PROVIDER_SPINNERS.get(_spinner_provider, _SPINNER_FRAMES_DEFAULT)
    label = PROVIDER_LABELS.get(_spinner_provider, "")
    color = PROVIDER_COLORS.get(_spinner_provider, JARVIS_BLUE)
    suffix = f" [{label}]" if label else ""
    i = 0
    while _spinner_active:
        frame = frames[i % len(frames)]
        sys.stdout.write(
            f"{CLEAR_LINE}    {color}{frame}{RESET} {DIM}{suffix}...{RESET}"
        )
        sys.stdout.flush()
        i += 1
        time.sleep(0.08)
