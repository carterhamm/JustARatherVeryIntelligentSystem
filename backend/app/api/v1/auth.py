"""Authentication endpoints — register, login, refresh, profile, preferences, passkeys.

JARVIS is a single-owner system. Registration requires the Secure Handshake
Token (SETUP_TOKEN) and is locked after the first user is created.
"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LookupRequest,
    LookupResponse,
    PasskeyLoginBeginRequest,
    PasskeyLoginCompleteRequest,
    PasskeyRegisterBeginRequest,
    PasskeyRegisterCompleteRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import AuthService

router = APIRouter()


# -- Setup status (no auth required) --------------------------------------

@router.get("/setup-status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    """Check if JARVIS has been set up (i.e. owner account exists)."""
    count = await db.scalar(select(func.count()).select_from(User))
    return {"setup_complete": bool(count and count > 0)}


# -- Single-owner registration (requires Secure Handshake Token) ----------

@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    x_setup_token: str | None = Header(None),
) -> AuthResponse:
    """Create the owner account. Requires SETUP_TOKEN header. Locked after first user."""
    # Verify Secure Handshake Token
    if not settings.SETUP_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. SETUP_TOKEN not configured on server.",
        )
    if not x_setup_token or x_setup_token != settings.SETUP_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Secure Handshake Token.",
        )

    # Only one user ever
    count = await db.scalar(select(func.count()).select_from(User))
    if count and count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. JARVIS is a single-owner system.",
        )
    return await AuthService.register(db, payload)


@router.post("/login", response_model=AuthResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    """Authenticate with email and password, receive JWT tokens with user data."""
    return await AuthService.login(db, payload.email, payload.password)


@router.post("/refresh", response_model=Token)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)) -> Token:
    """Exchange a valid refresh token for a new token pair."""
    return await AuthService.refresh_token(db, refresh_token)


# -- Passkey / WebAuthn endpoints -------------------------------------------

@router.post("/lookup", response_model=LookupResponse)
async def lookup(payload: LookupRequest, db: AsyncSession = Depends(get_db)) -> LookupResponse:
    """Check if an identifier (email or username) exists."""
    result = await AuthService.lookup(db, payload.identifier)
    return LookupResponse(**result)


@router.post("/register/begin")
async def passkey_register_begin(
    payload: PasskeyRegisterBeginRequest, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start WebAuthn registration — returns PublicKeyCredentialCreationOptions."""
    return await AuthService.begin_registration(
        db, email=payload.email, username=payload.username, full_name=payload.full_name,
    )


@router.post("/register/complete", response_model=AuthResponse, status_code=201)
async def passkey_register_complete(
    payload: PasskeyRegisterCompleteRequest, db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Complete WebAuthn registration, create user + credential, return tokens."""
    return await AuthService.complete_registration(
        db,
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        credential=payload.credential,
    )


@router.post("/login/begin")
async def passkey_login_begin(
    payload: PasskeyLoginBeginRequest, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start WebAuthn authentication — returns PublicKeyCredentialRequestOptions."""
    return await AuthService.begin_authentication(db, payload.identifier)


@router.post("/login/complete", response_model=AuthResponse)
async def passkey_login_complete(
    payload: PasskeyLoginCompleteRequest, db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Complete WebAuthn authentication, return tokens with user data."""
    return await AuthService.complete_authentication(
        db, identifier=payload.identifier, credential=payload.credential,
    )


# -- Profile & Preferences -------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the authenticated user's profile."""
    updated = await AuthService.update_user(db, current_user.id, payload)
    return UserResponse.model_validate(updated)


@router.get("/me/preferences")
async def get_preferences(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return the authenticated user's preferences."""
    return current_user.preferences or {}


@router.put("/me/preferences")
async def update_preferences(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Merge new preferences into the user's existing preferences."""
    existing = current_user.preferences or {}
    existing.update(payload)
    current_user.preferences = existing
    await db.commit()
    await db.refresh(current_user)
    return current_user.preferences or {}
