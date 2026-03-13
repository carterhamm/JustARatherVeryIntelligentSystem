"""AES-256 message encryption at rest.

Encrypts message content before database storage and decrypts on retrieval.
Uses per-user Fernet keys derived via PBKDF2-HMAC-SHA256 so each user's
messages are isolated even if the DB is compromised.

For Stark Protocol (local LLM) conversations, messages are encrypted both
at rest AND never leave the user's infrastructure. For Uplink providers
(Claude, Gemini), messages must be sent in plaintext to the provider API,
but are encrypted before storage in our database.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from functools import lru_cache
from typing import Optional
from uuid import UUID

from cryptography.fernet import Fernet

from app.config import settings

logger = logging.getLogger("jarvis.encryption")

_PBKDF2_ITERATIONS = settings.PBKDF2_ITERATIONS
_PBKDF2_KEY_LENGTH = 32  # 256 bits

# Prefix to identify encrypted content
_ENCRYPTED_PREFIX = "ENC::"


def _derive_key(user_id: UUID, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from master key + user ID + salt."""
    password = settings.AES_KEY.encode() + str(user_id).encode()
    dk = hashlib.pbkdf2_hmac(
        "sha256", password, salt, _PBKDF2_ITERATIONS, dklen=_PBKDF2_KEY_LENGTH,
    )
    return base64.urlsafe_b64encode(dk)


def encrypt_message(content: str, user_id: UUID) -> str:
    """Encrypt message content for at-rest storage.

    Returns a string in the format: ENC::<salt_b64>:<ciphertext>
    """
    if not content or not settings.AES_KEY:
        return content  # Skip encryption if no key configured

    salt = os.urandom(16)
    key = _derive_key(user_id, salt)
    cipher = Fernet(key).encrypt(content.encode()).decode()
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    return f"{_ENCRYPTED_PREFIX}{salt_b64}:{cipher}"


def decrypt_message(stored: str, user_id: UUID) -> str:
    """Decrypt message content from storage.

    Handles both encrypted (ENC:: prefixed) and plaintext (legacy) content.
    """
    if not stored or not stored.startswith(_ENCRYPTED_PREFIX):
        return stored  # Plaintext or empty — return as-is

    try:
        payload = stored[len(_ENCRYPTED_PREFIX):]
        salt_b64, cipher_text = payload.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_b64)
        key = _derive_key(user_id, salt)
        return Fernet(key).decrypt(cipher_text.encode()).decode()
    except Exception as exc:
        # If decryption fails (bad key, corrupted data), return a safe
        # placeholder rather than leaking ciphertext to the frontend
        logger.warning(
            "Decryption failed for user_id=%s: %s (returning placeholder)",
            user_id, type(exc).__name__,
        )
        return "[encrypted]"
