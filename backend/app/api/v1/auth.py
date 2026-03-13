"""Authentication endpoints — register, login, refresh, profile, preferences, passkeys.

JARVIS is a single-owner system. Registration requires the Secure Handshake
Token (SETUP_TOKEN) and is locked after the first user is created.
"""

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

logger = logging.getLogger(__name__)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.core.dependencies import get_current_active_user, get_current_active_user_or_service, get_db
from app.core.security import create_access_token, create_device_trust_token, create_refresh_token, create_totp_pending_token, decode_token, hash_password, verify_password
from app.db.redis import get_redis_client
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    CLIAuthRequest,
    CLISetupRequest,
    SetSHTRequest,
    LookupRequest,
    LookupResponse,
    PasskeyLoginBeginRequest,
    PasskeyLoginCompleteRequest,
    PasskeyRegisterBeginRequest,
    PasskeyRegisterCompleteRequest,
    TOTPLoginRequest,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import AuthService

router = APIRouter()

_TOTP_MAX_ATTEMPTS = 5
_TOTP_WINDOW_SECONDS = 900  # 15 minutes


async def _check_totp_rate_limit(user_id: str) -> None:
    """Block TOTP verification after too many failed attempts (5 per 15 min)."""
    try:
        redis = await get_redis_client()
        key = f"totp_attempts:{user_id}"
        attempts = await redis.cache_get(key)
        if attempts and int(attempts) >= _TOTP_MAX_ATTEMPTS:
            logger.warning("TOTP rate limit exceeded for user_id=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many TOTP attempts. Try again in 15 minutes.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # If Redis is down, fail open


async def _record_failed_totp(user_id: str) -> None:
    """Increment failed TOTP counter."""
    try:
        redis = await get_redis_client()
        key = f"totp_attempts:{user_id}"
        current = await redis.cache_get(key)
        count = int(current) + 1 if current else 1
        await redis.cache_set(key, str(count), ttl=_TOTP_WINDOW_SECONDS)
        logger.warning("Failed TOTP attempt for user_id=%s (attempt %d)", user_id, count)
    except Exception:
        pass


async def _clear_totp_attempts(user_id: str) -> None:
    """Clear TOTP attempt counter on success."""
    try:
        redis = await get_redis_client()
        key = f"totp_attempts:{user_id}"
        await redis.cache_delete(key)
    except Exception:
        pass


# -- Setup status (no auth required) --------------------------------------

@router.get("/setup-status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    """Check if JARVIS has been set up (i.e. owner account exists)."""
    count = await db.scalar(select(func.count()).select_from(User))
    return {"setup_complete": bool(count and count > 0)}


# -- Verify Setup Token (no auth required) ---------------------------------

@router.post("/verify-setup-token")
async def verify_setup_token(body: dict):
    """Verify a setup token without performing registration."""
    token = body.get("setup_token", "")
    if not token or token != settings.SETUP_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid setup token")
    return {"valid": True}


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

    # Max 2 users (owner + one trusted user)
    count = await db.scalar(select(func.count()).select_from(User))
    if count and count >= 2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Maximum users reached.",
        )
    return await AuthService.register(db, payload)


@router.post("/login", response_model=AuthResponse)
async def login(payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    """Authenticate with email and password, receive JWT tokens with user data."""
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    response = await AuthService.login(db, payload.email, payload.password, ip_address=client_ip)

    # Track session (best-effort, don't block login if this fails)
    try:
        from app.api.v1.sessions import create_session_record
        user = await AuthService.get_user_by_email(db, payload.email)
        if user:
            await create_session_record(db, user, request, "password")
    except Exception as exc:
        logger.warning("Failed to create session record: %s", exc)

    return response


@router.post("/refresh", response_model=Token)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)) -> Token:
    """Exchange a valid refresh token for a new token pair."""
    # Rate limit: max 1 refresh per 30 seconds per token
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    try:
        redis = await get_redis_client()
        rate_key = f"refresh_rate:{token_hash}"
        if await redis.cache_get(rate_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Token refresh rate limit exceeded. Try again in 30 seconds.",
            )
        await redis.cache_set(rate_key, "1", ttl=30)
    except HTTPException:
        raise
    except Exception:
        pass  # If Redis is down, fail open
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


@router.post("/login/complete")
async def passkey_login_complete(
    payload: PasskeyLoginCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse | dict:
    """Complete WebAuthn authentication, return tokens with user data.

    If TOTP 2FA is enabled, returns ``{"needs_totp": true, "totp_token": "..."}``
    instead of tokens — unless a valid device trust token is provided via
    the ``X-Device-Trust`` header (issued after prior TOTP verification,
    valid for 14 days).
    """
    auth_response = await AuthService.complete_authentication(
        db, identifier=payload.identifier, credential=payload.credential,
    )
    # Check if the user has TOTP enabled
    user = await AuthService.get_user_by_identifier(db, payload.identifier)
    if user:
        prefs = user.preferences or {}
        if prefs.get("totp_enabled"):
            # Read device trust from header directly (bypass FastAPI Header() mapping)
            device_trust = request.headers.get("x-device-trust")
            logger.info("Device trust header present: %s (user=%s)", bool(device_trust), user.id)
            if device_trust:
                try:
                    trust_data = decode_token(device_trust)
                    logger.info("Device trust decoded: type=%s, sub=%s, user=%s",
                                trust_data.type, trust_data.sub, user.id)
                    # Validate type, subject, AND device fingerprint
                    current_ua = request.headers.get("user-agent", "")
                    current_dh = hashlib.sha256(current_ua.encode()).hexdigest()
                    if (
                        trust_data.type == "device_trust"
                        and trust_data.sub == str(user.id)
                        and trust_data.dh == current_dh
                    ):
                        logger.info("Device trust valid — skipping TOTP for user %s", user.id)
                        return auth_response
                    logger.warning("Device trust token mismatch: type=%s, sub=%s vs user=%s, dh_match=%s",
                                   trust_data.type, trust_data.sub, user.id,
                                   trust_data.dh == current_dh)
                except Exception as exc:
                    logger.warning("Device trust token invalid/expired: %s", exc)
            totp_token = create_totp_pending_token(user.id)
            return {"needs_totp": True, "totp_token": totp_token}

    # Track session for passkey login
    if user:
        try:
            from app.api.v1.sessions import create_session_record
            await create_session_record(db, user, request, "passkey")
        except Exception as exc:
            logger.warning("Failed to create session record: %s", exc)

    return auth_response


# -- SHT management --------------------------------------------------------

@router.post("/set-sht", status_code=200)
async def set_sht(
    payload: SetSHTRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Set the Secure Handshake Token. Requires existing auth (JWT).

    The SHT is stored as a bcrypt hash in the user's preferences.
    It is required for all future CLI and site access.
    """
    prefs = dict(current_user.preferences or {})
    prefs["sht_hash"] = hash_password(payload.sht)
    current_user.preferences = prefs
    flag_modified(current_user, "preferences")
    await db.commit()
    return {"status": "ok", "message": "Secure Handshake Token set."}


# -- One-time CLI setup (Setup Token + username → store SHT) ---------------

@router.post("/cli-setup", status_code=200)
async def cli_setup(
    payload: CLISetupRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """One-time CLI setup: verify Setup Token, verify username exists, store SHT.

    Uses the server's SETUP_TOKEN to prove ownership. No JWT required.
    """
    if not settings.SETUP_TOKEN or payload.setup_token != settings.SETUP_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Setup Token.",
        )

    user = await AuthService.get_user_by_username(db, payload.username)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Username not found.",
        )

    prefs = dict(user.preferences or {})
    prefs["sht_hash"] = hash_password(payload.sht)
    user.preferences = prefs
    flag_modified(user, "preferences")
    await db.commit()

    return {"status": "ok", "username": user.username}


# -- CLI authentication (SHT + username → tokens) -------------------------

@router.post("/cli-login", response_model=AuthResponse)
async def cli_login(
    payload: CLIAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """CLI authentication: verify SHT and username, return JWT tokens.

    The SHT is checked against the bcrypt hash stored in the user's
    preferences (set via /set-sht). Rate-limited: 5 failures = 15 min lockout.
    """
    cli_key = f"cli:{payload.username}"
    await AuthService._check_login_rate_limit(cli_key)

    user = await AuthService.get_user_by_username(db, payload.username)
    if not user or not user.is_active:
        await AuthService._record_failed_login(cli_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    # Verify SHT against stored hash
    sht_hash = (user.preferences or {}).get("sht_hash")
    if not sht_hash or not verify_password(payload.sht, sht_hash):
        await AuthService._record_failed_login(cli_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    await AuthService._clear_login_attempts(cli_key)

    # Track session
    try:
        from app.api.v1.sessions import create_session_record
        await create_session_record(db, user, request, "cli_sht")
    except Exception as exc:
        logger.warning("Failed to create session record: %s", exc)

    return AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserResponse.model_validate(user),
    )


# -- TOTP 2FA ---------------------------------------------------------------

@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def totp_setup(
    current_user: User = Depends(get_current_active_user),
) -> TOTPSetupResponse:
    """Generate a TOTP secret. User must verify a code before it's enabled."""
    import pyotp
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email,
        issuer_name="J.A.R.V.I.S.",
    )
    return TOTPSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/totp/enable", status_code=200)
async def totp_enable(
    payload: TOTPVerifyRequest,
    secret: str = Header(..., alias="x-totp-secret"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Verify a TOTP code and permanently enable 2FA for this account."""
    import pyotp
    await _check_totp_rate_limit(str(current_user.id))
    totp = pyotp.TOTP(secret)
    if not totp.verify(payload.code, valid_window=1):
        await _record_failed_totp(str(current_user.id))
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    await _clear_totp_attempts(str(current_user.id))
    prefs = dict(current_user.preferences or {})
    prefs["totp_secret"] = secret
    prefs["totp_enabled"] = True
    current_user.preferences = prefs
    flag_modified(current_user, "preferences")
    await db.commit()
    return {"status": "ok", "message": "TOTP 2FA enabled."}


@router.post("/totp/disable", status_code=200)
async def totp_disable(
    payload: TOTPVerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Disable TOTP 2FA. Requires a valid code to confirm."""
    import pyotp
    await _check_totp_rate_limit(str(current_user.id))
    prefs = current_user.preferences or {}
    secret = prefs.get("totp_secret", "")
    if not secret:
        raise HTTPException(status_code=400, detail="TOTP not enabled.")
    totp = pyotp.TOTP(secret)
    if not totp.verify(payload.code, valid_window=1):
        await _record_failed_totp(str(current_user.id))
        raise HTTPException(status_code=400, detail="Invalid TOTP code.")
    await _clear_totp_attempts(str(current_user.id))
    prefs = dict(prefs)
    prefs.pop("totp_secret", None)
    prefs.pop("totp_enabled", None)
    current_user.preferences = prefs
    flag_modified(current_user, "preferences")
    await db.commit()
    return {"status": "ok", "message": "TOTP 2FA disabled."}


@router.get("/totp/status")
async def totp_status(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, bool]:
    """Check if TOTP 2FA is enabled for the current user."""
    prefs = current_user.preferences or {}
    return {"totp_enabled": bool(prefs.get("totp_enabled"))}


@router.get("/totp/code")
async def totp_code(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return the current TOTP code for the authenticated user.

    Requires a valid JWT — only accessible after full authentication.
    Used by the CLI to display codes like a phone authenticator app.
    """
    import pyotp
    import time as _time
    prefs = current_user.preferences or {}
    if not prefs.get("totp_enabled") or not prefs.get("totp_secret"):
        raise HTTPException(status_code=400, detail="TOTP not enabled.")
    totp = pyotp.TOTP(prefs["totp_secret"])
    now = _time.time()
    code = totp.now()
    remaining = 30 - int(now % 30)
    return {"code": code, "remaining": remaining, "period": 30}


@router.get("/totp/secret")
async def totp_secret(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return the TOTP secret for local code generation.

    Requires valid JWT. The CLI fetches this once to generate codes
    locally without repeated server calls.
    """
    prefs = current_user.preferences or {}
    if not prefs.get("totp_enabled") or not prefs.get("totp_secret"):
        raise HTTPException(status_code=400, detail="TOTP not enabled.")
    return {"secret": prefs["totp_secret"], "enabled": True}


@router.post("/login/totp-verify")
async def totp_login_verify(
    payload: TOTPLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Complete login with TOTP code after initial auth returned needs_totp.

    The totp_token is a short-lived JWT containing the user_id, issued
    when the initial login detected TOTP was enabled.

    On success, returns the standard auth response PLUS a ``device_trust_token``
    (14-day JWT) so the client can skip TOTP on future logins from this device.
    """
    try:
        token_data = decode_token(payload.totp_token)
        if token_data.type != "totp_pending":
            raise HTTPException(status_code=400, detail="Invalid TOTP token.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired TOTP token.")

    user_id = token_data.sub
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Access denied.")

    import pyotp
    await _check_totp_rate_limit(str(user.id))
    prefs = user.preferences or {}
    secret = prefs.get("totp_secret", "")
    if not secret:
        raise HTTPException(status_code=400, detail="TOTP not configured.")

    totp = pyotp.TOTP(secret)
    if not totp.verify(payload.code, valid_window=1):
        await _record_failed_totp(str(user.id))
        raise HTTPException(status_code=403, detail="Invalid TOTP code.")
    await _clear_totp_attempts(str(user.id))

    auth = AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserResponse.model_validate(user),
    )
    # Include a device trust token so they don't have to TOTP again for 14 days
    ua = request.headers.get("user-agent", "")
    return {
        **auth.model_dump(),
        "device_trust_token": create_device_trust_token(user.id, user_agent=ua),
    }


# -- Location (iOS Shortcuts / service key) ---------------------------------

@router.post("/me/location")
async def update_location(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update the user's current location. Called by iOS Shortcuts automations.

    Also logs the location to the history table for timeline display.
    """
    from datetime import datetime, timezone as tz
    from app.models.location_history import LocationHistory

    lat = payload.get("latitude")
    lng = payload.get("longitude")
    city = payload.get("city")
    state = payload.get("state")
    country = payload.get("country")

    # Update current location in preferences
    prefs = dict(current_user.preferences or {})
    prefs["current_location"] = {
        "latitude": lat,
        "longitude": lng,
        "city": city,
        "state": state,
        "country": country,
        "updated_at": payload.get("timestamp") or datetime.now(tz.utc).isoformat(),
    }
    current_user.preferences = prefs
    flag_modified(current_user, "preferences")

    # Log to location history for timeline
    if lat is not None and lng is not None:
        entry = LocationHistory(
            user_id=current_user.id,
            latitude=float(lat),
            longitude=float(lng),
            city=city,
            state=state,
            country=country,
        )
        db.add(entry)

    await db.commit()
    return {"status": "ok"}


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
    existing = dict(current_user.preferences or {})
    existing.update(payload)
    current_user.preferences = existing
    flag_modified(current_user, "preferences")
    await db.commit()
    await db.refresh(current_user)
    return current_user.preferences or {}
