"""Authentication business logic — registration, login, token refresh, user CRUD, passkeys."""

import json
import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger("jarvis.auth_service")

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.redis import get_redis_client
from app.models.passkey import PasskeyCredential
from app.models.user import User
from app.schemas.auth import AuthResponse, Token, UserCreate, UserResponse, UserUpdate


_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_SECONDS = 900  # 15 minutes


class AuthService:
    """Stateless service — every method receives the DB session explicitly."""

    # ------------------------------------------------------------------
    # Login rate limiting (brute-force protection)
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_login_rate_limit(email: str) -> None:
        """Block login attempts after too many failures. Uses Redis for tracking."""
        try:
            redis = await get_redis_client()
            key = f"login_attempts:{email.lower()}"
            attempts = await redis.cache_get(key)
            if attempts and int(attempts) >= _LOGIN_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Account temporarily locked — try again in 15 minutes.",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # If Redis is down, don't block login — fail open

    @staticmethod
    async def _record_failed_login(email: str) -> None:
        """Increment failed login counter for the email."""
        try:
            redis = await get_redis_client()
            key = f"login_attempts:{email.lower()}"
            current = await redis.cache_get(key)
            count = int(current) + 1 if current else 1
            await redis.cache_set(key, str(count), ttl=_LOGIN_LOCKOUT_SECONDS)
        except Exception:
            pass  # Best-effort — don't crash if Redis is down

    @staticmethod
    async def _clear_login_attempts(email: str) -> None:
        """Clear failed login counter on successful login."""
        try:
            redis = await get_redis_client()
            key = f"login_attempts:{email.lower()}"
            await redis.cache_delete(key)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Fetch a user by primary key."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Fetch a user by e-mail address."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """Fetch a user by username."""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @staticmethod
    async def register(db: AsyncSession, payload: UserCreate) -> AuthResponse:
        """Create a new user and return a JWT token pair with user data.

        Raises ``409 Conflict`` when the email or username is already taken.
        """
        user = User(
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
        )
        db.add(user)

        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            detail = "Email or username already registered"
            if "email" in str(exc.orig).lower():
                detail = "Email already registered"
            elif "username" in str(exc.orig).lower():
                detail = "Username already taken"
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc

        await db.commit()
        await db.refresh(user)

        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    @staticmethod
    async def login(db: AsyncSession, email: str, password: str) -> AuthResponse:
        """Verify credentials and return a JWT token pair with user data.

        Raises ``401 Unauthorized`` on bad credentials.
        Enforces brute-force protection: 5 failed attempts = 15 min lockout.
        """
        await AuthService._check_login_rate_limit(email)

        user = await AuthService.get_user_by_email(db, email)

        if user is None or not verify_password(password, user.hashed_password):
            await AuthService._record_failed_login(email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        await AuthService._clear_login_attempts(email)

        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    @staticmethod
    async def refresh_token(db: AsyncSession, refresh_token_str: str) -> Token:
        """Exchange a valid refresh token for a fresh token pair.

        Raises ``401 Unauthorized`` if the token is invalid or the user
        no longer exists.
        """
        payload = decode_token(refresh_token_str)

        if payload.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type — expected refresh token",
            )

        user = await AuthService.get_user_by_id(db, UUID(payload.sub))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    # ------------------------------------------------------------------
    # Profile update
    # ------------------------------------------------------------------

    @staticmethod
    async def update_user(db: AsyncSession, user_id: UUID, payload: UserUpdate) -> User:
        """Apply partial updates to the user's profile.

        Only fields that are explicitly set (not ``None``) are written.
        """
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        # Check username uniqueness if being updated
        if "username" in update_data:
            existing = await AuthService.get_user_by_username(db, update_data["username"])
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username already taken",
                )

        await db.execute(
            update(User).where(User.id == user_id).values(**update_data)
        )
        await db.commit()

        user = await AuthService.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found after update",
            )
        return user

    # ------------------------------------------------------------------
    # Passkey — lookup
    # ------------------------------------------------------------------

    @staticmethod
    async def lookup(db: AsyncSession, identifier: str) -> dict:
        """Check if an identifier (email or username) exists."""
        if "@" in identifier:
            user = await AuthService.get_user_by_email(db, identifier)
        else:
            user = await AuthService.get_user_by_username(db, identifier)
        if user and user.is_active:
            return {"exists": True, "user_id": user.id, "username": user.username}
        return {"exists": False}

    # ------------------------------------------------------------------
    # Passkey — registration
    # ------------------------------------------------------------------

    @staticmethod
    async def begin_registration(
        db: AsyncSession, email: str, username: str, full_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate WebAuthn registration options for a new user."""
        # Check uniqueness
        existing_email = await AuthService.get_user_by_email(db, email)
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        existing_username = await AuthService.get_user_by_username(db, username)
        if existing_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

        options = generate_registration_options(
            rp_id=settings.WEBAUTHN_RP_ID,
            rp_name=settings.WEBAUTHN_RP_NAME,
            user_name=email,
            user_display_name=full_name or username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
        )

        # Store challenge in Redis (60s TTL)
        redis = await get_redis_client()
        import base64
        challenge_b64 = base64.b64encode(options.challenge).decode()
        cache_key = f"webauthn:reg:{email}"
        await redis.cache_set(cache_key, challenge_b64, ttl=60)

        # Serialize options to JSON-compatible dict
        from webauthn.helpers import options_to_json
        return json.loads(options_to_json(options))

    @staticmethod
    async def complete_registration(
        db: AsyncSession,
        email: str,
        username: str,
        full_name: Optional[str],
        credential: dict[str, Any],
    ) -> AuthResponse:
        """Verify WebAuthn registration and create user + credential."""
        import base64
        from webauthn.helpers import parse_registration_credential_json

        redis = await get_redis_client()
        cache_key = f"webauthn:reg:{email}"
        stored_challenge = await redis.cache_get(cache_key)
        if not stored_challenge:
            raise HTTPException(status_code=400, detail="Registration challenge expired")
        await redis.cache_delete(cache_key)

        expected_challenge = base64.b64decode(stored_challenge)
        reg_credential = parse_registration_credential_json(json.dumps(credential))

        try:
            verification = verify_registration_response(
                credential=reg_credential,
                expected_challenge=expected_challenge,
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=settings.WEBAUTHN_ORIGIN,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Registration verification failed: {exc}") from exc

        # Create user (no password)
        user = User(email=email, username=username, full_name=full_name)
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            detail = "Email or username already registered"
            if "email" in str(exc.orig).lower():
                detail = "Email already registered"
            elif "username" in str(exc.orig).lower():
                detail = "Username already taken"
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc

        # Store credential
        passkey = PasskeyCredential(
            user_id=user.id,
            credential_id=verification.credential_id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
            device_name=credential.get("authenticatorAttachment", "platform"),
            transports=credential.get("response", {}).get("transports"),
        )
        db.add(passkey)
        await db.commit()
        await db.refresh(user)

        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )

    # ------------------------------------------------------------------
    # Passkey — authentication
    # ------------------------------------------------------------------

    @staticmethod
    async def begin_authentication(db: AsyncSession, identifier: str) -> dict[str, Any]:
        """Generate WebAuthn authentication options for an existing user."""
        if "@" in identifier:
            user = await AuthService.get_user_by_email(db, identifier)
        else:
            user = await AuthService.get_user_by_username(db, identifier)

        if not user or not user.is_active:
            raise HTTPException(status_code=404, detail="User not found")

        # Get user's passkeys
        result = await db.execute(
            select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)
        )
        passkeys = result.scalars().all()
        if not passkeys:
            raise HTTPException(status_code=400, detail="No passkeys registered for this user")

        allow_credentials = []
        for pk in passkeys:
            # Convert stored transport strings to AuthenticatorTransport enums
            transport_enums = []
            for t in (pk.transports or []):
                try:
                    transport_enums.append(AuthenticatorTransport(t))
                except ValueError:
                    pass  # Skip unknown transport types
            allow_credentials.append(
                PublicKeyCredentialDescriptor(
                    id=pk.credential_id,
                    transports=transport_enums,
                )
            )

        options = generate_authentication_options(
            rp_id=settings.WEBAUTHN_RP_ID,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        # Store challenge in Redis
        import base64
        try:
            redis = await get_redis_client()
            challenge_b64 = base64.b64encode(options.challenge).decode()
            cache_key = f"webauthn:auth:{identifier}"
            await redis.cache_set(cache_key, challenge_b64, ttl=60)
        except Exception as exc:
            logger.error("Redis unavailable during auth begin: %s", exc)
            raise HTTPException(status_code=503, detail="Cache service unavailable, please try again") from exc

        from webauthn.helpers import options_to_json
        return json.loads(options_to_json(options))

    @staticmethod
    async def complete_authentication(
        db: AsyncSession, identifier: str, credential: dict[str, Any],
    ) -> AuthResponse:
        """Verify WebAuthn authentication and return tokens."""
        import base64
        from webauthn.helpers import parse_authentication_credential_json

        if "@" in identifier:
            user = await AuthService.get_user_by_email(db, identifier)
        else:
            user = await AuthService.get_user_by_username(db, identifier)

        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            redis = await get_redis_client()
            cache_key = f"webauthn:auth:{identifier}"
            stored_challenge = await redis.cache_get(cache_key)
            if not stored_challenge:
                raise HTTPException(status_code=400, detail="Authentication challenge expired")
            await redis.cache_delete(cache_key)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Redis unavailable during auth complete: %s", exc)
            raise HTTPException(status_code=503, detail="Cache service unavailable, please try again") from exc

        expected_challenge = base64.b64decode(stored_challenge)
        auth_credential = parse_authentication_credential_json(json.dumps(credential))

        # Find the matching passkey by raw_id from the parsed credential
        result = await db.execute(
            select(PasskeyCredential).where(
                PasskeyCredential.user_id == user.id,
                PasskeyCredential.credential_id == auth_credential.raw_id,
            )
        )
        passkey = result.scalar_one_or_none()

        if not passkey:
            raise HTTPException(status_code=401, detail="Credential not recognized")

        try:
            verification = verify_authentication_response(
                credential=auth_credential,
                expected_challenge=expected_challenge,
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=settings.WEBAUTHN_ORIGIN,
                credential_public_key=passkey.public_key,
                credential_current_sign_count=passkey.sign_count,
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc

        # Update sign count
        passkey.sign_count = verification.new_sign_count
        await db.commit()

        return AuthResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            user=UserResponse.model_validate(user),
        )

    # ------------------------------------------------------------------
    # Deactivation
    # ------------------------------------------------------------------

    @staticmethod
    async def deactivate_user(db: AsyncSession, user_id: UUID) -> User:
        """Soft-delete a user by setting ``is_active = False``."""
        await db.execute(
            update(User).where(User.id == user_id).values(is_active=False)
        )
        await db.commit()

        user = await AuthService.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user
