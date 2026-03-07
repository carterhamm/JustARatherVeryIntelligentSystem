"""Minimal input UI — ANSI-styled prompt using plain input().

No prompt_toolkit. No screen takeover. Just a compact 2-line input
that renders inline and doesn't interfere with terminal scrollback.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time

# ANSI colours
_BLUE = "\x1b[38;2;0;212;255m"
_DIM = "\x1b[38;2;51;52;64m"
_BOLD = "\x1b[1m"
_RESET = "\x1b[0m"

PROVIDER_COLORS = {
    "claude": "\x1b[38;2;255;140;0m",
    "gemini": "\x1b[38;2;59;130;246m",
    "stark_protocol": "\x1b[38;2;239;68;68m",
}

PROVIDER_LABELS = {
    "claude": "Claude",
    "gemini": "Gemini",
    "stark_protocol": "Stark Protocol",
}

PROVIDERS = ["claude", "gemini", "stark_protocol"]


class JarvisInput:
    """Compact terminal input with ANSI styling."""

    def __init__(self, initial_provider: str = "gemini") -> None:
        self.provider = initial_provider
        self._last_ctrl_c: float = 0

    def _draw_separator(self) -> None:
        """Print separator line with provider name right-aligned."""
        cols = shutil.get_terminal_size().columns
        label = PROVIDER_LABELS.get(self.provider, self.provider)
        color = PROVIDER_COLORS.get(self.provider, _BLUE)
        label_len = len(label) + 1
        line_len = max(cols - label_len, 10)
        sys.stdout.write(
            f"{_DIM}{'─' * line_len}{_RESET}{color} {label}{_RESET}\n"
        )
        sys.stdout.flush()

    async def async_get_input(self) -> str:
        """Async input — renders a compact 2-line prompt inline."""
        self._draw_separator()
        prompt = f"  {_BLUE}{_BOLD}❯ {_RESET}"
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, lambda: input(prompt))
            return result.strip()
        except KeyboardInterrupt:
            now = time.time()
            if now - self._last_ctrl_c < 1.5:
                raise
            self._last_ctrl_c = now
            sys.stdout.write(
                f"\n  \x1b[38;2;75;85;99mPress Ctrl+C again to exit\x1b[0m\n"
            )
            sys.stdout.flush()
            return ""

    def get_input(self) -> str:
        """Sync version."""
        self._draw_separator()
        prompt = f"  {_BLUE}{_BOLD}❯ {_RESET}"
        return input(prompt).strip()
