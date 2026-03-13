"""Reusable FastAPI dependencies for database sessions, caching, and auth."""

import logging
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, get_current_user
from app.db.postgres import get_session
from app.db.redis import get_redis_client, RedisClient
from app.models.user import User
from app.schemas.auth import TokenPayload

logger = logging.getLogger("jarvis.dependencies")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session, rolling back on error.

    If the database is unreachable, raises HTTP 503 instead of letting
    the raw connection error propagate as an unhandled 500.
    """
    try:
        async for session in get_session():
            yield session
    except OSError as exc:
        logger.error("Database connection failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable. Please try again shortly.",
        )
    except Exception as exc:
        # Catch SQLAlchemy connection errors, asyncpg errors, etc.
        exc_name = type(exc).__name__
        if any(kw in exc_name.lower() for kw in ("connect", "timeout", "refused", "unavailable")):
            logger.error("Database connection failed (%s): %s", exc_name, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database temporarily unavailable. Please try again shortly.",
            )
        raise


async def get_redis() -> RedisClient:
    """Return the shared Redis client.

    Returns the client even if Redis is down -- callers should handle
    redis errors themselves.  This prevents the dependency from blocking
    endpoints that don't strictly need caching.
    """
    return await get_redis_client()


async def get_current_active_user(
    token_payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the JWT into a full ``User`` ORM instance and ensure the account is active."""
    result = await db.execute(select(User).where(User.id == token_payload.sub))
    user = result.scalar_one_or_none()

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

    return user


async def get_user_from_token_or_query(
    request: Request,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via JWT in Authorization header OR ``?token=`` query param.

    Needed for endpoints consumed by ``<img>`` / ``<video>`` tags that cannot
    set HTTP headers (e.g. MJPEG streams).
    """
    from app.core.security import decode_token as _decode

    jwt: str | None = token  # query param
    if not jwt:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            jwt = auth_header[7:]
    if not jwt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (Bearer token or ?token= query)",
        )

    payload = _decode(jwt)
    if payload.type != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
    return user


async def get_current_active_user_or_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via ``X-Service-Key`` header **or** standard JWT Bearer.

    Checks service key first (for daemons like the wake listener that run
    24/7 and can't do JWT refresh loops), then falls back to JWT.
    """
    from app.config import settings

    # Path 1: Service API key (X-Service-Key header)
    service_key = request.headers.get("x-service-key")
    if service_key:
        if not settings.SERVICE_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Service key auth not configured on server",
            )
        if service_key != settings.SERVICE_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid service key",
            )
        # Return the owner (first active user — single-owner system)
        result = await db.execute(
            select(User).where(User.is_active.is_(True)).limit(1)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No active user found",
            )
        return user

    # Path 2: Standard JWT Bearer token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
        except HTTPException:
            raise
        if payload.type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        result = await db.execute(select(User).where(User.id == payload.sub))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (Bearer token or X-Service-Key)",
        headers={"WWW-Authenticate": "Bearer"},
    )
