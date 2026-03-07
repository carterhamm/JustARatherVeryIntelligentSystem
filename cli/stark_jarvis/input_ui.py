"""Rich input UI — Claude Code-style input with JARVIS theming and model picker.

Uses prompt_toolkit for multi-line input, key bindings, and styled toolbar.
"""

from __future__ import annotations

import shutil
import sys
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

# JARVIS colour palette for prompt_toolkit styles
JARVIS_STYLE = Style.from_dict({
    # Input area — light gray text on black bg
    "": "#e5e7eb bg:#000000",
    "prompt": "#00d4ff bold",
    "separator": "#333340",

    # Bottom toolbar
    "bottom-toolbar": "noinherit bg:#000000",
    "bottom-toolbar.separator": "#333340",
    "bottom-toolbar.provider-claude": "#ff8c00",
    "bottom-toolbar.provider-gemini": "#3b82f6",
    "bottom-toolbar.provider-stark_protocol": "#ef4444",

    # Model picker overlay
    "dialog": "bg:#1a1a2e",
    "dialog.body": "bg:#1a1a2e #e5e7eb",
    "dialog frame.label": "#00d4ff bold",
})

PROVIDERS = [
    ("claude", "Claude", "#ff8c00"),
    ("gemini", "Gemini", "#3b82f6"),
    ("stark_protocol", "Stark Protocol", "#ef4444"),
]

PROVIDER_STYLE_MAP = {
    "claude": "class:bottom-toolbar.provider-claude",
    "gemini": "class:bottom-toolbar.provider-gemini",
    "stark_protocol": "class:bottom-toolbar.provider-stark_protocol",
}

PROVIDER_LABELS = {
    "claude": "Claude",
    "gemini": "Gemini",
    "stark_protocol": "Stark Protocol",
}


class JarvisInput:
    """Rich terminal input with JARVIS theming and inline model picker."""

    def __init__(self, initial_provider: str = "claude") -> None:
        self.provider = initial_provider
        self._picker_active = False
        self._last_ctrl_c: float = 0

        # Key bindings
        self._kb = KeyBindings()

        # Ctrl+T: cycle model
        @self._kb.add("c-t")
        def _cycle_model(event):
            ids = [p[0] for p in PROVIDERS]
            idx = ids.index(self.provider) if self.provider in ids else 0
            self.provider = ids[(idx + 1) % len(ids)]

        # Enter: submit
        @self._kb.add("enter")
        def _submit(event):
            buf = event.app.current_buffer
            text = buf.text.strip()
            if text:
                buf.validate_and_handle()

        # Double Ctrl+C to exit
        @self._kb.add("c-c")
        def _exit(event):
            import time
            now = time.time()
            if now - self._last_ctrl_c < 1.5:
                event.app.current_buffer.text = ""
                raise KeyboardInterrupt
            self._last_ctrl_c = now
            event.app.current_buffer.text = ""
            sys.stdout.write(
                f"\n  \x1b[38;2;75;85;99mPress Ctrl+C again to exit\x1b[0m\n"
            )
            sys.stdout.flush()

        self._session: Optional[PromptSession] = None

    def _get_session(self) -> PromptSession:
        if self._session is None:
            self._session = PromptSession(
                style=JARVIS_STYLE,
                key_bindings=self._kb,
                multiline=False,
                mouse_support=False,
                bottom_toolbar=self._toolbar,
                placeholder=HTML(
                    '<style fg="#4b5563" bg="#000000">Message J.A.R.V.I.S.</style>'
                ),
            )
        return self._session

    def _toolbar(self) -> list:
        """Bottom bar: separator line with model name right-aligned."""
        provider_style = PROVIDER_STYLE_MAP.get(
            self.provider, "class:bottom-toolbar.provider-claude"
        )
        provider_label = PROVIDER_LABELS.get(self.provider, self.provider)

        cols = shutil.get_terminal_size().columns
        label_len = len(provider_label) + 1  # space before label
        line_len = max(cols - label_len, 10)

        return [
            ("class:bottom-toolbar.separator", "─" * line_len),
            (provider_style, f" {provider_label}"),
        ]

    def _prompt_text(self) -> list:
        """Prompt prefix with separator line above."""
        cols = shutil.get_terminal_size().columns
        return [
            ("class:separator", "─" * cols + "\n"),
            ("class:prompt", "  ❯ "),
        ]

    def get_input(self) -> str:
        """Prompt for input with the rich UI. Raises EOFError/KeyboardInterrupt on exit."""
        session = self._get_session()
        return session.prompt(self._prompt_text).strip()
