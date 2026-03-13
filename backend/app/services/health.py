"""
Lightweight service health checker for JARVIS graceful degradation.

Unlike ``system_monitor.py`` (which is a detailed dashboard tool with caching
and latency metrics), this module answers a simpler question at startup and
on-demand: "which services are *available right now*?"

Each check is wrapped in try/except with a short timeout so a single
unreachable service never blocks the whole application.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("jarvis.services.health")

# Per-check timeout in seconds
_CHECK_TIMEOUT = 5.0


class ServiceHealth:
    """Probes core JARVIS infrastructure and returns availability status."""

    @classmethod
    async def check_all(cls) -> dict[str, dict[str, Any]]:
        """Run every health probe concurrently and return a status dict.

        Returns a mapping like::

            {
                "redis":    {"ok": True,  "latency_ms": 12},
                "postgres": {"ok": True,  "latency_ms": 34},
                "qdrant":   {"ok": False, "error": "Connection refused"},
                "gemini":   {"ok": True,  "detail": "API key present"},
                "camera":   {"ok": False, "error": "Not configured"},
            }
        """
        checks = {
            "redis": cls._check_redis,
            "postgres": cls._check_postgres,
            "qdrant": cls._check_qdrant,
            "gemini": cls._check_gemini_key,
            "camera": cls._check_camera_proxy,
        }

        results: dict[str, dict[str, Any]] = {}
        tasks = {
            name: asyncio.create_task(cls._safe_run(fn))
            for name, fn in checks.items()
        }

        for name, task in tasks.items():
            results[name] = await task

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    async def _safe_run(cls, fn) -> dict[str, Any]:
        """Execute *fn* with a timeout, catching all exceptions."""
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(fn(), timeout=_CHECK_TIMEOUT)
            result.setdefault("latency_ms", round((time.monotonic() - t0) * 1000))
            return result
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": f"Timed out after {_CHECK_TIMEOUT}s",
                "latency_ms": round((time.monotonic() - t0) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "latency_ms": round((time.monotonic() - t0) * 1000),
            }

    # ------------------------------------------------------------------
    # Individual probes
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_redis() -> dict[str, Any]:
        from app.db.redis import get_redis_client

        client = await get_redis_client()
        pong = await client.client.ping()
        return {"ok": bool(pong)}

    @staticmethod
    async def _check_postgres() -> dict[str, Any]:
        from sqlalchemy import text
        from app.db.postgres import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True}

    @staticmethod
    async def _check_qdrant() -> dict[str, Any]:
        from app.db.qdrant import get_qdrant_store

        store = get_qdrant_store()
        await store.initialize()
        count = await store.count()
        return {"ok": True, "detail": f"{count} points"}

    @staticmethod
    async def _check_gemini_key() -> dict[str, Any]:
        from app.config import settings

        key = settings.GOOGLE_GEMINI_API_KEY
        if key and key != "placeholder":
            return {"ok": True, "detail": "API key present"}
        return {"ok": False, "error": "GOOGLE_GEMINI_API_KEY not configured"}

    @staticmethod
    async def _check_camera_proxy() -> dict[str, Any]:
        from app.config import settings

        url = settings.CAMERA_PROXY_URL
        if not url:
            return {"ok": False, "error": "CAMERA_PROXY_URL not configured"}

        import httpx

        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            resp = await client.get(url.rstrip("/") + "/health")
        if resp.status_code == 200:
            return {"ok": True}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
