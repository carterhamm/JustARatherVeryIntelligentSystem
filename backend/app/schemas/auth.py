"""Pydantic v2 schemas for authentication and user management."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserCreate(BaseModel):
    """Payload for registering a new user."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=256)


class UserLogin(BaseModel):
    """Payload for logging in."""

    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Payload for updating the current user's profile."""

    full_name: Optional[str] = Field(default=None, max_length=256)
    username: Optional[str] = Field(default=None, min_length=3, max_length=64)


class UserResponse(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """JWT token pair returned after login / register / refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Token pair + user object returned after login / register."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str
    exp: Optional[int] = None
    type: str = "access"


# -- Passkey / WebAuthn schemas -----------------------------------------------

class LookupRequest(BaseModel):
    """Check if an identifier (email or username) exists."""
    identifier: str = Field(min_length=1, max_length=320)


class LookupResponse(BaseModel):
    exists: bool
    user_id: Optional[UUID] = None
    username: Optional[str] = None


class PasskeyRegisterBeginRequest(BaseModel):
    """Start passkey registration for a new user."""
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    full_name: Optional[str] = Field(default=None, max_length=256)
    setup_token: Optional[str] = None


class PasskeyRegisterCompleteRequest(BaseModel):
    """Complete passkey registration with the credential response."""
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    full_name: Optional[str] = None
    credential: dict[str, Any]
    setup_token: Optional[str] = None


class PasskeyLoginBeginRequest(BaseModel):
    """Start passkey authentication for an existing user."""
    identifier: str = Field(min_length=1, max_length=320)


class PasskeyLoginCompleteRequest(BaseModel):
    """Complete passkey authentication with the assertion response."""
    identifier: str = Field(min_length=1, max_length=320)
    credential: dict[str, Any]


class CLIAuthRequest(BaseModel):
    """CLI authentication: SHT + JARVIS username → JWT tokens."""
    sht: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=64)


class SetSHTRequest(BaseModel):
    """Set the Secure Handshake Token (requires auth)."""
    sht: str = Field(min_length=4, max_length=256)


class CLISetupRequest(BaseModel):
    """One-time CLI setup: Setup Token + username + SHT."""
    setup_token: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=64)
    sht: str = Field(min_length=4, max_length=256)
