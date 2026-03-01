"""Pydantic v2 schemas for authentication and user management."""

from datetime import datetime
from typing import Optional
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


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str
    exp: Optional[int] = None
    type: str = "access"
