"""Shared metrics collection and aggregation for JARVIS autonomy."""

from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any

from app.db.redis import get_redis_client

logger = logging.getLogger("jarvis.autonomy.metrics")

_TTL_30_DAYS = 60 * 60 * 24 * 30


def _redis_key(namespace: str, key: str) -> str:
    return f"jarvis:autonomy:metrics:{namespace}:{key}"


async def record_metric(
    namespace: str,
    key: str,
    value: float,
    tags: dict[str, Any] | None = None,
) -> None:
    """Store a metric data point in Redis.

    Each entry is appended as JSON to a list at
    ``jarvis:autonomy:metrics:{namespace}:{key}`` with a 30-day TTL.
    """
    try:
        redis = await get_redis_client()
        entry = {
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tags": tags or {},
        }
        rkey = _redis_key(namespace, key)
        await redis.client.rpush(rkey, json.dumps(entry))
        await redis.client.expire(rkey, _TTL_30_DAYS)
    except Exception:
        logger.warning("Failed to record metric %s:%s", namespace, key, exc_info=True)


async def get_metrics(
    namespace: str,
    key: str,
    since_hours: int = 24,
) -> list[dict]:
    """Retrieve metric history filtered by age.

    Returns entries recorded within the last *since_hours* hours, newest last.
    """
    try:
        redis = await get_redis_client()
        rkey = _redis_key(namespace, key)
        raw_entries = await redis.client.lrange(rkey, 0, -1)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        results: list[dict] = []

        for raw in raw_entries:
            try:
                entry = json.loads(raw)
                ts = datetime.fromisoformat(entry["timestamp"])
                if ts >= cutoff:
                    results.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        return results
    except Exception:
        logger.warning("Failed to get metrics %s:%s", namespace, key, exc_info=True)
        return []


async def compute_baseline(
    namespace: str,
    key: str,
    window_days: int = 7,
) -> dict[str, float]:
    """Compute p50, p95, and mean from metric history.

    Uses the last *window_days* days of data. Returns an empty dict if
    insufficient data is available.
    """
    try:
        entries = await get_metrics(namespace, key, since_hours=window_days * 24)
        values = [e["value"] for e in entries if isinstance(e.get("value"), (int, float))]

        if not values:
            return {}

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        p50_idx = max(0, int(n * 0.50) - 1)
        p95_idx = max(0, int(n * 0.95) - 1)

        return {
            "mean": statistics.mean(values),
            "p50": sorted_vals[p50_idx],
            "p95": sorted_vals[p95_idx],
        }
    except Exception:
        logger.warning(
            "Failed to compute baseline %s:%s", namespace, key, exc_info=True
        )
        return {}
