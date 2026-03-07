"""Persistent configuration — stores gate credentials, SHT hash, and settings."""

from __future__ import annotations

import json
import hashlib
import base64
import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

# Default JARVIS server
DEFAULT_SERVER = "https://app.malibupoint.dev"

# Session timing
SESSION_TTL = 1800      # 30 minutes — session valid without re-auth
PURGE_TTL = 5400        # 90 minutes — wipe all JARVIS data from machine

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

    # ── Session management ────────────────────────────────────────────────

    def save_session(self, access_token: str, refresh_token: str) -> None:
        """Store session tokens and mark last activity."""
        self._data["session_access"] = access_token
        self._data["session_refresh"] = refresh_token
        self._data["last_active"] = time.time()
        self._save()

    def touch_session(self) -> None:
        """Update last activity timestamp."""
        self._data["last_active"] = time.time()
        self._save()

    def get_session(self) -> Optional[tuple[str, str]]:
        """Return (access_token, refresh_token) if session is still valid, else None."""
        last_active = self._data.get("last_active")
        if not last_active:
            return None
        elapsed = time.time() - last_active
        if elapsed > SESSION_TTL:
            self.clear_session()
            return None
        access = self._data.get("session_access", "")
        refresh = self._data.get("session_refresh", "")
        if not access or not refresh:
            return None
        return access, refresh

    def clear_session(self) -> None:
        """Remove session tokens only (keep gate creds + config)."""
        for k in ("session_access", "session_refresh", "last_active"):
            self._data.pop(k, None)
        self._save()

    def check_auto_purge(self) -> bool:
        """If inactive for > PURGE_TTL, wipe everything. Returns True if purged."""
        last_active = self._data.get("last_active")
        if not last_active:
            return False
        if time.time() - last_active > PURGE_TTL:
            self.purge()
            return True
        return False

    # ── Cleanup ──────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Nuke everything — full logout + unlink."""
        self._data = {}
        self._save()
        if SALT_FILE.exists():
            SALT_FILE.unlink()

    def purge(self) -> None:
        """Remove entire ~/.jarvis/ directory."""
        self._data = {}
        if CONFIG_DIR.exists():
            shutil.rmtree(CONFIG_DIR)


config = JarvisConfig()
