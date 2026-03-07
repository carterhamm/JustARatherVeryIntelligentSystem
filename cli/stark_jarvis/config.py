"""Persistent configuration — stores gate credentials, SHT hash, and settings."""

from __future__ import annotations

import json
import hashlib
import base64
import os
from pathlib import Path
from typing import Any, Optional

# Default JARVIS server
DEFAULT_SERVER = "https://app.malibupoint.dev"

# Config lives in ~/.jarvis/
CONFIG_DIR = Path.home() / ".jarvis"
CONFIG_FILE = CONFIG_DIR / "config.json"
SALT_FILE = CONFIG_DIR / ".salt"


def _get_salt() -> bytes:
    """Return (or create) a persistent random salt for key derivation."""
    if SALT_FILE.exists():
        return SALT_FILE.read_bytes()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(32)
    SALT_FILE.write_bytes(salt)
    SALT_FILE.chmod(0o600)
    return salt


class JarvisConfig:
    """Manages the persistent JARVIS CLI configuration."""

    def __init__(self) -> None:
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if CONFIG_FILE.exists():
            try:
                self._data = json.loads(CONFIG_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._data, indent=2))
        CONFIG_FILE.chmod(0o600)

    # ── Generic get/set ──────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    # ── Server URL ───────────────────────────────────────────────────────

    @property
    def server_url(self) -> Optional[str]:
        return self._data.get("server_url")

    @server_url.setter
    def server_url(self, url: str) -> None:
        self._data["server_url"] = url.rstrip("/")
        self._save()

    # ── Model provider ───────────────────────────────────────────────────

    @property
    def model_provider(self) -> str:
        return self._data.get("model_provider", "claude")

    @model_provider.setter
    def model_provider(self, provider: str) -> None:
        self._data["model_provider"] = provider
        self._save()

    # ── Setup check ──────────────────────────────────────────────────────

    def is_setup(self) -> bool:
        """True if first-time setup has been completed."""
        return all(
            self._data.get(k)
            for k in ("gate_username_hash", "gate_password_hash", "sht_hash", "server_url")
        )

    # ── Cleanup ──────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Nuke everything — full logout + unlink."""
        self._data = {}
        self._save()
        if SALT_FILE.exists():
            SALT_FILE.unlink()


config = JarvisConfig()
