"""Rich input UI — Claude Code-style input with JARVIS theming and model picker.

Uses prompt_toolkit for multi-line input, key bindings, and styled toolbar.
"""

from __future__ import annotations

from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.keys import Keys

# JARVIS colour palette for prompt_toolkit styles
JARVIS_STYLE = Style.from_dict({
    # Input area
    "": "#e5e7eb",                          # default text — light gray
    "prompt": "#00d4ff bold",               # prompt arrow — jarvis blue
    "prompt.model": "#ffaa00 bold",         # model label in prompt

    # Bottom toolbar
    "bottom-toolbar": "bg:#0f0f14 #4b5563",
    "bottom-toolbar.key": "#00d4ff bold",
    "bottom-toolbar.model": "#ffaa00 bold",
    "bottom-toolbar.provider-claude": "#ff8c00 bold",
    "bottom-toolbar.provider-gemini": "#3b82f6 bold",
    "bottom-toolbar.provider-stark_protocol": "#ef4444 bold",
    "bottom-toolbar.sep": "#4b5563",
    "bottom-toolbar.hint": "#4b5563",

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

        # Key bindings
        self._kb = KeyBindings()

        # Ctrl+M: cycle model
        @self._kb.add("c-t")
        def _cycle_model(event):
            ids = [p[0] for p in PROVIDERS]
            idx = ids.index(self.provider) if self.provider in ids else 0
            self.provider = ids[(idx + 1) % len(ids)]

        # Enter: submit (unless shift+enter for newline)
        @self._kb.add("enter")
        def _submit(event):
            buf = event.app.current_buffer
            text = buf.text.strip()
            if text:
                buf.validate_and_handle()

        # Shift+Enter: insert newline
        @self._kb.add("s-enter")
        def _newline(event):
            event.app.current_buffer.insert_text("\n")

        # Ctrl+C: exit
        @self._kb.add("c-c")
        def _exit(event):
            event.app.current_buffer.text = ""
            raise KeyboardInterrupt

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
                    '<style fg="#4b5563">Message J.A.R.V.I.S.</style>'
                ),
            )
        return self._session

    def _toolbar(self) -> list:
        """Build the bottom toolbar showing model + shortcuts."""
        provider_style = PROVIDER_STYLE_MAP.get(self.provider, "class:bottom-toolbar.model")
        provider_label = PROVIDER_LABELS.get(self.provider, self.provider)

        return [
            ("class:bottom-toolbar.key", " Ctrl+T "),
            ("class:bottom-toolbar.hint", "model "),
            (provider_style, f" {provider_label} "),
            ("class:bottom-toolbar.sep", "  │  "),
            ("class:bottom-toolbar.key", "Enter "),
            ("class:bottom-toolbar.hint", "send  "),
            ("class:bottom-toolbar.key", "Shift+Enter "),
            ("class:bottom-toolbar.hint", "newline  "),
            ("class:bottom-toolbar.sep", "│  "),
            ("class:bottom-toolbar.key", "/help "),
            ("class:bottom-toolbar.hint", "commands"),
        ]

    def _prompt_text(self) -> list:
        """Build the styled prompt prefix."""
        return [
            ("class:prompt", "❯ "),
        ]

    def get_input(self) -> str:
        """Prompt for input with the rich UI. Raises EOFError/KeyboardInterrupt on exit."""
        session = self._get_session()
        return session.prompt(self._prompt_text).strip()
