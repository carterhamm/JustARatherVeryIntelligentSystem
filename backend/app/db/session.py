"""Session utilities — re-exports and a transaction context manager."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import async_session_factory, engine, get_session

# Re-export for convenience
__all__ = ["async_session_factory", "engine", "get_session", "transaction"]


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations.

    Usage::

        async with transaction() as session:
            session.add(some_object)
            # commit happens automatically on clean exit
            # rollback happens on exception
    """
    async with async_session_factory() as session:
        async with session.begin():
            yield session
