"""Security utilities — password hashing, JWT tokens, AES encryption, PBKDF2."""

import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.auth import TokenPayload

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` when *plain* matches *hashed*."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def create_access_token(subject: str | UUID, extra_claims: Optional[dict[str, Any]] = None) -> str:
    """Create a short-lived access JWT."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | UUID) -> str:
    """Create a long-lived refresh JWT."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_totp_pending_token(subject: str | UUID) -> str:
    """Create a short-lived token for TOTP verification (5 minutes)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "totp_pending",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_device_trust_token(subject: str | UUID, user_agent: str = "") -> str:
    """Create a long-lived device trust token (14 days).

    After successful TOTP verification, this token is returned to the client.
    On subsequent logins from the same device, the client sends this token
    to skip the TOTP step.

    Includes a SHA-256 hash of the user-agent for device fingerprinting.
    """
    expire = datetime.now(timezone.utc) + timedelta(days=14)
    device_hash = hashlib.sha256(user_agent.encode()).hexdigest()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "device_trust",
        "dh": device_hash,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT, returning the payload."""
    try:
        raw = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return TokenPayload(**raw)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------------
# AES encryption (Fernet)
# ---------------------------------------------------------------------------

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.AES_KEY.encode())
    return _fernet


def encrypt_value(plain_text: str) -> str:
    """Encrypt *plain_text* and return a URL-safe base-64 string."""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_value(cipher_text: str) -> str:
    """Decrypt a Fernet token back to plain text."""
    return _get_fernet().decrypt(cipher_text.encode()).decode()


# ---------------------------------------------------------------------------
# PBKDF2 per-user key derivation (for OAuth token encryption)
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 480_000
_PBKDF2_KEY_LENGTH = 32  # 256 bits


def derive_user_key(user_id: str | UUID, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a per-user Fernet key using PBKDF2-HMAC-SHA256.

    Returns ``(derived_key_bytes, salt)``.  Store the salt alongside the
    encrypted data so it can be reproduced later.
    """
    if salt is None:
        salt = os.urandom(16)

    master = settings.AES_KEY.encode()
    # Combine master key with user ID for per-user isolation
    password = master + str(user_id).encode()

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password,
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_PBKDF2_KEY_LENGTH,
    )

    # Fernet requires a URL-safe base64-encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(dk)
    return fernet_key, salt


def encrypt_user_value(plain_text: str, user_id: str | UUID) -> str:
    """Encrypt a value with a per-user derived key.

    Returns ``salt_b64:cipher_text`` so the salt is stored alongside.
    """
    fernet_key, salt = derive_user_key(user_id)
    f = Fernet(fernet_key)
    cipher = f.encrypt(plain_text.encode()).decode()
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    return f"{salt_b64}:{cipher}"


def decrypt_user_value(stored: str, user_id: str | UUID) -> str:
    """Decrypt a value encrypted with :func:`encrypt_user_value`."""
    salt_b64, cipher_text = stored.split(":", 1)
    salt = base64.urlsafe_b64decode(salt_b64)
    fernet_key, _ = derive_user_key(user_id, salt=salt)
    f = Fernet(fernet_key)
    return f.decrypt(cipher_text.encode()).decode()


# ---------------------------------------------------------------------------
# FastAPI dependency: get current user from JWT
# ---------------------------------------------------------------------------


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> TokenPayload:
    """Extract and return the authenticated user's token payload.

    This is a lightweight dependency that only validates the JWT.  For a
    full ``User`` ORM object see ``get_current_active_user`` in
    ``core.dependencies``.
    """
    payload = decode_token(token)
    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
