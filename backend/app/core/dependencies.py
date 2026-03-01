"""Reusable FastAPI dependencies for database sessions, caching, and auth."""

from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.postgres import get_session
from app.db.redis import get_redis_client, RedisClient
from app.models.user import User
from app.schemas.auth import TokenPayload


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session, rolling back on error."""
    async for session in get_session():
        yield session


async def get_redis() -> RedisClient:
    """Return the shared Redis client."""
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
