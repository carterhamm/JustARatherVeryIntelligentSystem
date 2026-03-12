"""JARVIS System Health Monitor.

Checks every JARVIS subsystem in parallel and returns a consolidated health
report.  Results are cached in Redis with a 5-minute TTL so dashboard widgets
and JARVIS tool calls never hammer the downstream services.

Systems monitored:
  - Railway Backend         (self-check via /health)
  - Mac Mini Agent          (MAC_MINI_AGENT_URL/health)
  - Mac Mini LM Studio      (stark.malibupoint.dev/v1/models)
  - Mac Mini XTTS Voice     (voice.malibupoint.dev/health)
  - Qdrant Cloud            (vector store client ping)
  - Redis                   (PING round-trip)
  - PostgreSQL              (simple SELECT 1)
  - ElevenLabs API          (GET /v1/user)
  - Gemini API              (GET models endpoint)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.system_monitor")

# Redis cache key and TTL (seconds)
_CACHE_KEY = "jarvis:system_health"
_CACHE_TTL = 300  # 5 minutes

# HTTP timeout per check (seconds)
_TIMEOUT = 5.0


# ═════════════════════════════════════════════════════════════════════════════
# Individual health check functions
# ═════════════════════════════════════════════════════════════════════════════

async def _check_http(
    name: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> dict[str, Any]:
    """Generic HTTP GET health check."""
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers or {})
        latency_ms = round((time.monotonic() - t0) * 1000)
        if resp.status_code == expected_status:
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
        else:
            return {
                "status": "degraded",
                "latency_ms": latency_ms,
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "error": f"HTTP {resp.status_code}",
            }
    except httpx.TimeoutException:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": "timeout",
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }


async def _check_railway_backend() -> dict[str, Any]:
    return await _check_http("railway_backend", "https://app.malibupoint.dev/health")


async def _check_mac_mini_agent() -> dict[str, Any]:
    agent_url = settings.MAC_MINI_AGENT_URL
    if not agent_url:
        return {
            "status": "down",
            "latency_ms": 0,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": "MAC_MINI_AGENT_URL not configured",
        }
    url = agent_url.rstrip("/") + "/health"
    headers = {}
    if settings.MAC_MINI_AGENT_KEY:
        headers["Authorization"] = f"Bearer {settings.MAC_MINI_AGENT_KEY}"
    return await _check_http("mac_mini_agent", url, headers=headers)


async def _check_mac_mini_lm_studio() -> dict[str, Any]:
    """Check LM Studio via Cloudflare tunnel: stark.malibupoint.dev/v1/models."""
    return await _check_http(
        "mac_mini_lm_studio",
        "https://stark.malibupoint.dev/v1/models",
    )


async def _check_mac_mini_voice() -> dict[str, Any]:
    """Check XTTS voice server: voice.malibupoint.dev/health."""
    return await _check_http(
        "mac_mini_voice",
        "https://voice.malibupoint.dev/health",
    )


async def _check_qdrant() -> dict[str, Any]:
    """Check Qdrant Cloud by hitting the collections endpoint."""
    t0 = time.monotonic()
    try:
        from app.db.qdrant import get_qdrant_store

        store = get_qdrant_store()
        # Ensure the client is initialised (idempotent)
        await store.initialize()
        count = await store.count()
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "detail": f"{count} points",
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }


async def _check_redis() -> dict[str, Any]:
    """Check Redis with a PING round-trip."""
    t0 = time.monotonic()
    try:
        from app.db.redis import get_redis_client

        r = await get_redis_client()
        # Direct ping via underlying aioredis client
        pong = await r.client.ping()
        latency_ms = round((time.monotonic() - t0) * 1000)
        if pong:
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "status": "degraded",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": "PING returned falsy",
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }


async def _check_postgres() -> dict[str, Any]:
    """Check PostgreSQL with SELECT 1."""
    t0 = time.monotonic()
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.DATABASE_URL, pool_size=1, max_overflow=0)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }


async def _check_elevenlabs() -> dict[str, Any]:
    """Quick ElevenLabs API check via /v1/user."""
    if not settings.ELEVENLABS_API_KEY:
        return {
            "status": "down",
            "latency_ms": 0,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": "ELEVENLABS_API_KEY not configured",
        }
    return await _check_http(
        "elevenlabs",
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
    )


async def _check_gemini() -> dict[str, Any]:
    """Quick Gemini API check — list models endpoint."""
    if not settings.GOOGLE_GEMINI_API_KEY:
        return {
            "status": "down",
            "latency_ms": 0,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": "GOOGLE_GEMINI_API_KEY not configured",
        }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
        f"?key={settings.GOOGLE_GEMINI_API_KEY}&pageSize=1"
    )
    return await _check_http("gemini", url)


# ═════════════════════════════════════════════════════════════════════════════
# Overall health aggregator
# ═════════════════════════════════════════════════════════════════════════════

async def get_system_health(*, force_refresh: bool = False) -> dict[str, Any]:
    """Check health of all JARVIS subsystems and return a consolidated status.

    Results are cached in Redis for 5 minutes.  Pass ``force_refresh=True``
    to bypass the cache and re-probe all systems immediately.
    """
    if not force_refresh:
        try:
            from app.db.redis import get_redis_client

            r = await get_redis_client()
            cached = await r.cache_get(_CACHE_KEY)
            if cached:
                data = json.loads(cached)
                data["from_cache"] = True
                return data
        except Exception:
            pass  # cache miss — fall through to live checks

    logger.info("System health: running live checks on all subsystems")

    # All checks run in parallel
    results = await asyncio.gather(
        _check_railway_backend(),
        _check_mac_mini_agent(),
        _check_mac_mini_lm_studio(),
        _check_mac_mini_voice(),
        _check_qdrant(),
        _check_redis(),
        _check_postgres(),
        _check_elevenlabs(),
        _check_gemini(),
        return_exceptions=True,
    )

    names = [
        "railway_backend",
        "mac_mini_agent",
        "mac_mini_lm_studio",
        "mac_mini_voice",
        "qdrant",
        "redis",
        "postgres",
        "elevenlabs",
        "gemini",
    ]

    systems: dict[str, Any] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            systems[name] = {
                "status": "down",
                "latency_ms": 0,
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "error": str(result),
            }
        else:
            systems[name] = result

    # Derive overall status
    statuses = [s["status"] for s in systems.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "down" for s in statuses):
        overall = "degraded"
    else:
        overall = "degraded"

    # Count by status
    healthy_count = sum(1 for s in statuses if s == "healthy")
    down_count = sum(1 for s in statuses if s == "down")

    payload = {
        "overall": overall,
        "healthy_count": healthy_count,
        "down_count": down_count,
        "total_systems": len(systems),
        "systems": systems,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
    }

    # Cache result in Redis
    try:
        from app.db.redis import get_redis_client

        r = await get_redis_client()
        await r.cache_set(_CACHE_KEY, json.dumps(payload, default=str), ttl=_CACHE_TTL)
    except Exception as exc:
        logger.warning("Failed to cache system health: %s", exc)

    return payload


async def get_railway_deploy_status() -> dict[str, Any]:
    """Fetch the latest Railway deployment status for the backend service.

    Uses the Railway GraphQL API with a project-scoped token.
    Returns deployment info including status, creator, and timestamp.
    """
    _RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"
    _TOKEN = "90e04bb8-a13d-46b5-b1d9-abc8641d70f0"
    _SERVICE_ID = "adb6b312-0380-40aa-91e5-39c047a52ee2"

    query = """
    query GetLatestDeployment($serviceId: String!) {
      deployments(
        input: { serviceId: $serviceId }
        first: 1
      ) {
        edges {
          node {
            id
            status
            createdAt
            updatedAt
            meta
            url
            canRedeploy
          }
        }
      }
    }
    """

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RAILWAY_GRAPHQL,
                json={"query": query, "variables": {"serviceId": _SERVICE_ID}},
                headers={
                    "Authorization": f"Bearer {_TOKEN}",
                    "Content-Type": "application/json",
                    "User-Agent": "JARVIS/1.0",
                },
            )
        latency_ms = round((time.monotonic() - t0) * 1000)

        if resp.status_code != 200:
            return {
                "error": f"Railway API returned HTTP {resp.status_code}",
                "latency_ms": latency_ms,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        data = resp.json()
        if "errors" in data:
            return {
                "error": data["errors"][0].get("message", "GraphQL error"),
                "latency_ms": latency_ms,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        edges = data.get("data", {}).get("deployments", {}).get("edges", [])
        if not edges:
            return {
                "error": "No deployments found",
                "latency_ms": latency_ms,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        node = edges[0]["node"]
        meta = node.get("meta") or {}

        return {
            "deployment_id": node.get("id", ""),
            "status": node.get("status", "UNKNOWN"),
            "created_at": node.get("createdAt", ""),
            "updated_at": node.get("updatedAt", ""),
            "url": node.get("url", ""),
            "can_redeploy": node.get("canRedeploy", False),
            "commit_sha": meta.get("commitHash", "")[:7] if meta.get("commitHash") else "",
            "commit_message": meta.get("commitMessage", ""),
            "branch": meta.get("branch", ""),
            "latency_ms": latency_ms,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except httpx.TimeoutException:
        return {
            "error": "Railway API timed out",
            "latency_ms": round((time.monotonic() - t0) * 1000),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "latency_ms": round((time.monotonic() - t0) * 1000),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
