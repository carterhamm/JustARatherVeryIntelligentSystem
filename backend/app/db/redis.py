"""Async Redis client with caching helpers."""

import ssl
from typing import Any, Optional

import redis.asyncio as aioredis

from app.config import settings


class RedisClient:
    """Thin wrapper around an async Redis connection with convenience methods."""

    def __init__(self) -> None:
        kwargs: dict[str, Any] = {
            "decode_responses": True,
        }
        # Use TLS when the URL scheme is rediss://
        if settings.REDIS_URL.startswith("rediss://"):
            ssl_ctx = ssl.create_default_context()
            kwargs["ssl"] = ssl_ctx
        self.client: aioredis.Redis = aioredis.from_url(
            settings.REDIS_URL,
            **kwargs,
        )

    async def cache_get(self, key: str) -> Optional[str]:
        """Retrieve a cached value by *key*, or ``None`` if missing/expired."""
        return await self.client.get(key)

    async def cache_set(self, key: str, value: str, ttl: int = 300) -> None:
        """Store *value* under *key* with an expiry of *ttl* seconds."""
        await self.client.set(key, value, ex=ttl)

    async def cache_delete(self, key: str) -> None:
        """Delete a single key from the cache."""
        await self.client.delete(key)

    async def close(self) -> None:
        """Gracefully close the underlying connection pool."""
        await self.client.aclose()


# Module-level singleton — initialised lazily via get_redis_client()
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """Return (and lazily create) the shared :class:`RedisClient` singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def close_redis() -> None:
    """Close the singleton Redis client if it exists."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
