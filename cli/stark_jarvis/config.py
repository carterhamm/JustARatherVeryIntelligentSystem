"""Persistent configuration — stores server URL + encrypted auth tokens."""

from __future__ import annotations

import json
import hashlib
import base64
import os
from pathlib import Path
from typing import Optional

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


def _derive_key(password: str) -> bytes:
    """Derive a 32-byte Fernet key from a password + salt."""
    salt = _get_salt()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=600_000, dklen=32)
    return base64.urlsafe_b64encode(dk)


def _encrypt(data: str, password: str) -> str:
    """Encrypt a string with the given password."""
    from cryptography.fernet import Fernet
    key = _derive_key(password)
    return Fernet(key).encrypt(data.encode()).decode()


def _decrypt(token: str, password: str) -> str:
    """Decrypt a string with the given password."""
    from cryptography.fernet import Fernet
    key = _derive_key(password)
    return Fernet(key).decrypt(token.encode()).decode()


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

    @property
    def server_url(self) -> Optional[str]:
        return self._data.get("server_url")

    @server_url.setter
    def server_url(self, url: str) -> None:
        self._data["server_url"] = url.rstrip("/")
        self._save()

    @property
    def model_provider(self) -> str:
        return self._data.get("model_provider", "claude")

    @model_provider.setter
    def model_provider(self, provider: str) -> None:
        self._data["model_provider"] = provider
        self._save()

    def save_auth(self, access_token: str, refresh_token: str, password: str) -> None:
        """Encrypt and store auth tokens."""
        self._data["access_token"] = _encrypt(access_token, password)
        self._data["refresh_token"] = _encrypt(refresh_token, password)
        self._data["auth_check"] = _encrypt("jarvis_auth_ok", password)
        self._save()

    def load_auth(self, password: str) -> tuple[Optional[str], Optional[str]]:
        """Decrypt and return (access_token, refresh_token). Returns (None, None) on failure."""
        try:
            # Verify password first
            check = self._data.get("auth_check")
            if not check or _decrypt(check, password) != "jarvis_auth_ok":
                return None, None
            access = _decrypt(self._data["access_token"], password)
            refresh = _decrypt(self._data["refresh_token"], password)
            return access, refresh
        except Exception:
            return None, None

    def has_auth(self) -> bool:
        return "access_token" in self._data and "auth_check" in self._data

    def clear_auth(self) -> None:
        """Remove stored credentials."""
        for key in ("access_token", "refresh_token", "auth_check"):
            self._data.pop(key, None)
        self._save()

    def clear_all(self) -> None:
        """Nuke everything — full logout + unlink."""
        self._data = {}
        self._save()
        # Remove salt too so nothing can be recovered
        if SALT_FILE.exists():
            SALT_FILE.unlink()


config = JarvisConfig()
