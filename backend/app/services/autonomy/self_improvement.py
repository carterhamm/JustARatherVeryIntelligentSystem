"""Pillar 4: Self-Improvement Loop for JARVIS.

Tracks performance metrics, detects capability gaps, monitors resources,
and generates weekly self-improvement reports. Every function degrades
gracefully — a failure in one subsystem never blocks the rest.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.redis import get_redis_client
from app.db.session import async_session_factory
from app.integrations.llm.factory import get_llm_client
from app.models.conversation import Message
from app.services.autonomy.metrics import record_metric, get_metrics, compute_baseline

logger = logging.getLogger("jarvis.autonomy.self_improvement")

# ── TTL constants (seconds) ─────────────────────────────────────────────
_TTL_14_DAYS = 60 * 60 * 24 * 14
_TTL_30_DAYS = 60 * 60 * 24 * 30
_TTL_90_DAYS = 60 * 60 * 24 * 90
_TTL_365_DAYS = 60 * 60 * 24 * 365

# ── Redis key prefixes ──────────────────────────────────────────────────
_KEY_TOOL_STATS = "jarvis:autonomy:improve:tool_stats"
_KEY_QUALITY_SIGNALS = "jarvis:autonomy:improve:quality_signals"
_KEY_CAPABILITY_GAPS = "jarvis:autonomy:improve:capability_gaps"
_KEY_RESOURCE_USAGE = "jarvis:autonomy:improve:resource_usage"
_KEY_WEEKLY_REPORT = "jarvis:autonomy:improve:weekly_report"

# ── Quality signal patterns ─────────────────────────────────────────────
_NEGATIVE_SIGNALS = [
    "that's wrong",
    "no not that",
    "try again",
    "fix it",
    "that's not right",
    "not what i asked",
    "incorrect",
    "you got it wrong",
    "wrong answer",
    "that doesn't work",
    "not helpful",
    "please fix",
]

_POSITIVE_SIGNALS = [
    "thanks",
    "thank you",
    "perfect",
    "great",
    "awesome",
    "excellent",
    "well done",
    "good job",
    "nice",
    "love it",
    "exactly",
    "that's right",
]

# ── Railway GraphQL ─────────────────────────────────────────────────────
_RAILWAY_GQL_URL = "https://backboard.railway.com/graphql/v2"

_MAX_TOOL_STATS_ENTRIES = 10_000


# ═════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════


async def run_improvement_cycle() -> dict[str, Any]:
    """Execute one full self-improvement cycle.

    Phase 1: Aggregate tool execution stats from Redis
    Phase 2: Detect quality signals from recent conversations
    Phase 3: Identify capability gaps
    Phase 4: Monitor resource usage

    Results are persisted to Redis and returned as a summary dict.
    """
    logger.info("Self-improvement cycle starting")
    now = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "status": "ok",
    }

    # ── Phase 1: Tool execution stats ────────────────────────────────
    try:
        tool_stats = await _aggregate_tool_stats()
        result["tool_stats"] = tool_stats
        await record_metric("self_improvement", "tool_stats_collected", 1.0)
    except Exception as exc:
        logger.warning("Phase 1 (tool stats) failed: %s", exc, exc_info=True)
        result["tool_stats"] = {"error": str(exc)}

    # ── Phase 2: Quality signals ─────────────────────────────────────
    try:
        signals = await _detect_quality_signals()
        result["quality_signals"] = {
            "count": len(signals),
            "positive": sum(1 for s in signals if s["signal"] == "positive"),
            "negative": sum(1 for s in signals if s["signal"] == "negative"),
            "samples": signals[:10],
        }

        # Persist today's signals
        today = now.strftime("%Y-%m-%d")
        redis = await get_redis_client()
        await redis.cache_set(
            f"{_KEY_QUALITY_SIGNALS}:{today}",
            json.dumps(signals, default=str),
            ttl=_TTL_90_DAYS,
        )
    except Exception as exc:
        logger.warning("Phase 2 (quality signals) failed: %s", exc, exc_info=True)
        result["quality_signals"] = {"error": str(exc)}

    # ── Phase 3: Capability gaps ─────────────────────────────────────
    try:
        gaps = await _detect_capability_gaps()
        result["capability_gaps"] = gaps

        redis = await get_redis_client()
        await redis.cache_set(
            _KEY_CAPABILITY_GAPS,
            json.dumps(gaps, default=str),
            ttl=_TTL_30_DAYS,
        )
    except Exception as exc:
        logger.warning("Phase 3 (capability gaps) failed: %s", exc, exc_info=True)
        result["capability_gaps"] = {"error": str(exc)}

    # ── Phase 4: Resource usage ──────────────────────────────────────
    try:
        resources = await _monitor_resource_usage()
        result["resource_usage"] = resources
    except Exception as exc:
        logger.warning("Phase 4 (resource usage) failed: %s", exc, exc_info=True)
        result["resource_usage"] = {"error": str(exc)}

    # ── Store combined result ────────────────────────────────────────
    try:
        redis = await get_redis_client()
        await redis.cache_set(
            "jarvis:autonomy:improve:last_cycle",
            json.dumps(result, default=str),
            ttl=_TTL_30_DAYS,
        )
    except Exception:
        logger.warning("Failed to store improvement cycle result", exc_info=True)

    logger.info(
        "Self-improvement cycle complete: %d tool stats, %d quality signals, %d gaps",
        result.get("tool_stats", {}).get("total_executions", 0),
        result.get("quality_signals", {}).get("count", 0),
        len(result.get("capability_gaps", [])) if isinstance(result.get("capability_gaps"), list) else 0,
    )
    return result


async def track_tool_execution(
    tool_name: str,
    success: bool,
    latency_ms: int,
    error: str = "",
) -> None:
    """Record a single tool execution event.

    Called by the agent executor after each tool call. Entries are
    appended to a Redis list with a 365-day TTL, capped at 10 000
    entries (oldest trimmed).
    """
    try:
        redis = await get_redis_client()
        entry = {
            "tool": tool_name,
            "success": success,
            "latency_ms": latency_ms,
            "error": error[:500] if error else "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await redis.client.rpush(_KEY_TOOL_STATS, json.dumps(entry))
        await redis.client.expire(_KEY_TOOL_STATS, _TTL_365_DAYS)

        # Trim to keep only the most recent entries
        length = await redis.client.llen(_KEY_TOOL_STATS)
        if length > _MAX_TOOL_STATS_ENTRIES:
            trim_count = length - _MAX_TOOL_STATS_ENTRIES
            await redis.client.ltrim(_KEY_TOOL_STATS, trim_count, -1)

        # Also record as a metric for baseline computation
        await record_metric(
            "tool_execution",
            tool_name,
            latency_ms,
            tags={"success": success, "error": error[:200] if error else ""},
        )
    except Exception:
        logger.debug("Failed to track tool execution for %s", tool_name, exc_info=True)


async def generate_weekly_report() -> dict[str, Any]:
    """Compile and store a comprehensive weekly self-improvement report.

    Synthesises tool stats, quality signals, capability gaps, resource
    usage, learning metrics, and code health into a narrative report
    using Gemini.
    """
    logger.info("Generating weekly self-improvement report")
    now = datetime.now(timezone.utc)
    week_number = now.strftime("%Y-W%W")

    report: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "week": week_number,
    }

    # ── Tool stats (last 7 days) ─────────────────────────────────────
    try:
        report["tool_stats"] = await _aggregate_tool_stats(days=7)
    except Exception as exc:
        logger.warning("Weekly report: tool stats failed: %s", exc)
        report["tool_stats"] = {"error": str(exc)}

    # ── Quality signals trend ────────────────────────────────────────
    try:
        report["quality_trend"] = await _get_quality_trend(days=7)
    except Exception as exc:
        logger.warning("Weekly report: quality trend failed: %s", exc)
        report["quality_trend"] = {"error": str(exc)}

    # ── Capability gaps ──────────────────────────────────────────────
    try:
        redis = await get_redis_client()
        gaps_raw = await redis.cache_get(_KEY_CAPABILITY_GAPS)
        report["capability_gaps"] = json.loads(gaps_raw) if gaps_raw else []
    except Exception as exc:
        logger.warning("Weekly report: capability gaps failed: %s", exc)
        report["capability_gaps"] = {"error": str(exc)}

    # ── Resource usage trends ────────────────────────────────────────
    try:
        report["resource_trends"] = await _get_resource_trend(days=7)
    except Exception as exc:
        logger.warning("Weekly report: resource trends failed: %s", exc)
        report["resource_trends"] = {"error": str(exc)}

    # ── Learning metrics ─────────────────────────────────────────────
    try:
        from app.services.continuous_learning import get_learning_metrics
        report["learning_metrics"] = await get_learning_metrics()
    except Exception as exc:
        logger.warning("Weekly report: learning metrics failed: %s", exc)
        report["learning_metrics"] = {"error": str(exc)}

    # ── Code health ──────────────────────────────────────────────────
    try:
        from app.services.autonomy.code_manager import get_code_health_report
        report["code_health"] = await get_code_health_report()
    except ImportError:
        report["code_health"] = {"status": "module_not_available"}
    except Exception as exc:
        logger.warning("Weekly report: code health failed: %s", exc)
        report["code_health"] = {"error": str(exc)}

    # ── LLM narrative synthesis ──────────────────────────────────────
    try:
        narrative = await _synthesize_report_narrative(report)
        report["narrative"] = narrative
    except Exception as exc:
        logger.warning("Weekly report: narrative synthesis failed: %s", exc)
        report["narrative"] = f"Report synthesis unavailable: {exc}"

    # ── Persist ──────────────────────────────────────────────────────
    try:
        redis = await get_redis_client()
        report_json = json.dumps(report, default=str)

        await redis.cache_set(
            f"{_KEY_WEEKLY_REPORT}:latest",
            report_json,
            ttl=_TTL_14_DAYS,
        )
        await redis.cache_set(
            f"{_KEY_WEEKLY_REPORT}:{week_number}",
            report_json,
            ttl=_TTL_90_DAYS,
        )
    except Exception:
        logger.warning("Failed to persist weekly report", exc_info=True)

    logger.info("Weekly self-improvement report generated for %s", week_number)
    return report


async def get_improvement_report() -> dict[str, Any]:
    """Return the latest weekly report from Redis, or an empty status dict."""
    try:
        redis = await get_redis_client()
        raw = await redis.cache_get(f"{_KEY_WEEKLY_REPORT}:latest")
        if raw:
            return json.loads(raw)
        return {"status": "no_report_available"}
    except Exception as exc:
        logger.warning("Failed to retrieve improvement report: %s", exc)
        return {"status": "error", "error": str(exc)}


# ═════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════


async def _aggregate_tool_stats(days: int = 1) -> dict[str, Any]:
    """Parse tool execution entries from Redis and compute aggregates."""
    redis = await get_redis_client()
    raw_entries = await redis.client.lrange(_KEY_TOOL_STATS, 0, -1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries: list[dict] = []

    for raw in raw_entries:
        try:
            entry = json.loads(raw)
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                entries.append(entry)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    if not entries:
        return {"total_executions": 0, "period_days": days}

    # Aggregate by tool name
    tool_counts: Counter[str] = Counter()
    tool_failures: Counter[str] = Counter()
    tool_latencies: dict[str, list[int]] = {}

    for e in entries:
        name = e.get("tool", "unknown")
        tool_counts[name] += 1
        if not e.get("success", True):
            tool_failures[name] += 1
        lat = e.get("latency_ms", 0)
        tool_latencies.setdefault(name, []).append(lat)

    # Most used, most failed, slowest
    most_used = tool_counts.most_common(10)
    most_failed = tool_failures.most_common(10)

    avg_latencies = {
        name: sum(lats) / len(lats) for name, lats in tool_latencies.items() if lats
    }
    slowest = sorted(avg_latencies.items(), key=lambda x: x[1], reverse=True)[:10]

    total_success = sum(1 for e in entries if e.get("success", True))
    total_fail = len(entries) - total_success

    return {
        "total_executions": len(entries),
        "period_days": days,
        "success_count": total_success,
        "failure_count": total_fail,
        "success_rate": round(total_success / len(entries) * 100, 1) if entries else 0,
        "most_used": [{"tool": t, "count": c} for t, c in most_used],
        "most_failed": [{"tool": t, "failures": c} for t, c in most_failed],
        "slowest": [{"tool": t, "avg_latency_ms": round(l, 1)} for t, l in slowest],
    }


async def _detect_quality_signals() -> list[dict]:
    """Scan recent user messages for positive and negative quality signals."""
    signals: list[dict] = []

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        async with async_session_factory() as session:
            stmt = (
                select(Message)
                .where(
                    Message.role == "user",
                    Message.created_at >= cutoff,
                )
                .order_by(Message.created_at.desc())
                .limit(500)
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()

        for msg in messages:
            content = _safe_decrypt_content(msg)
            if not content:
                continue

            content_lower = content.lower()
            ts = msg.created_at.isoformat() if msg.created_at else ""
            preview = content[:100]

            for pattern in _NEGATIVE_SIGNALS:
                if pattern in content_lower:
                    signals.append({
                        "signal": "negative",
                        "pattern": pattern,
                        "message_preview": preview,
                        "timestamp": ts,
                    })
                    break

            for pattern in _POSITIVE_SIGNALS:
                if pattern in content_lower:
                    signals.append({
                        "signal": "positive",
                        "pattern": pattern,
                        "message_preview": preview,
                        "timestamp": ts,
                    })
                    break

    except Exception as exc:
        logger.warning("Quality signal detection failed: %s", exc, exc_info=True)

    return signals


def _safe_decrypt_content(msg: Message) -> str:
    """Attempt to decrypt message content; return empty string on failure."""
    try:
        content = msg.content or ""
        if not content.startswith("ENC::"):
            return content

        # Encrypted content requires a user_id from the conversation
        from app.core.encryption import decrypt_message
        conv = getattr(msg, "conversation", None)
        if conv and hasattr(conv, "user_id"):
            return decrypt_message(content, conv.user_id)

        # Cannot decrypt without user_id — skip gracefully
        return ""
    except Exception:
        return ""


async def _detect_capability_gaps() -> list[dict]:
    """Use Gemini to analyze recent tool failures and identify capability gaps."""
    gaps: list[dict] = []

    try:
        # Gather recent tool failures
        redis = await get_redis_client()
        raw_entries = await redis.client.lrange(_KEY_TOOL_STATS, -2000, -1)

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        failures: list[dict] = []

        for raw in raw_entries:
            try:
                entry = json.loads(raw)
                if not entry.get("success", True):
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if ts >= cutoff:
                        failures.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        # Group failures by tool
        failure_groups: dict[str, list[str]] = {}
        for f in failures:
            tool = f.get("tool", "unknown")
            err = f.get("error", "")[:200]
            failure_groups.setdefault(tool, []).append(err)

        if not failure_groups:
            return []

        # Build analysis prompt
        failure_summary = "\n".join(
            f"- {tool}: {len(errs)} failures. Sample errors: {'; '.join(set(errs[:3]))}"
            for tool, errs in failure_groups.items()
        )

        prompt = (
            "You are JARVIS's self-improvement system. Analyze these tool failure patterns "
            "from the last 7 days and identify capability gaps.\n\n"
            f"Tool failures:\n{failure_summary}\n\n"
            "For each gap identified, return a JSON array of objects with keys:\n"
            '- "gap": brief description of the capability gap\n'
            '- "evidence": what data supports this gap\n'
            '- "suggested_solution": concrete recommendation to fix it\n\n'
            "Return ONLY valid JSON. If no gaps, return []."
        )

        llm = get_llm_client()
        response = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )

        content = response.get("content", "").strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        parsed = json.loads(content)
        if isinstance(parsed, list):
            gaps = [
                {
                    "gap": g.get("gap", ""),
                    "evidence": g.get("evidence", ""),
                    "suggested_solution": g.get("suggested_solution", ""),
                }
                for g in parsed
                if isinstance(g, dict) and g.get("gap")
            ]

    except json.JSONDecodeError:
        logger.warning("Capability gap analysis returned invalid JSON")
    except Exception as exc:
        logger.warning("Capability gap detection failed: %s", exc, exc_info=True)

    return gaps


async def _monitor_resource_usage() -> dict[str, Any]:
    """Query Railway metrics for resource usage and store a daily snapshot."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    result: dict[str, Any] = {"timestamp": now.isoformat()}

    # Try Railway GraphQL for metrics
    try:
        metrics = await _query_railway_metrics()
        result.update(metrics)
    except Exception as exc:
        logger.debug("Railway metrics unavailable: %s", exc)
        result["railway_metrics"] = {"status": "unavailable", "error": str(exc)}

    # Basic health check fallback
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://app.malibupoint.dev/health")
            result["health_check"] = {
                "status_code": resp.status_code,
                "healthy": resp.status_code == 200,
                "latency_ms": int(resp.elapsed.total_seconds() * 1000),
            }
    except Exception as exc:
        result["health_check"] = {"healthy": False, "error": str(exc)}

    # Store daily snapshot
    try:
        redis = await get_redis_client()
        await redis.cache_set(
            f"{_KEY_RESOURCE_USAGE}:{today}",
            json.dumps(result, default=str),
            ttl=_TTL_30_DAYS,
        )
    except Exception:
        logger.debug("Failed to store resource snapshot", exc_info=True)

    return result


async def _query_railway_metrics() -> dict[str, Any]:
    """Query Railway GraphQL API for service resource metrics."""
    if not settings.RAILWAY_API_TOKEN or not settings.RAILWAY_SERVICE_ID:
        return {"status": "not_configured"}

    query = """
    query($serviceId: String!, $environmentId: String!) {
      deployments(
        first: 1
        input: {
          serviceId: $serviceId
          environmentId: $environmentId
        }
      ) {
        edges {
          node {
            id
            status
            createdAt
          }
        }
      }
    }
    """

    headers = {
        "Authorization": f"Bearer {settings.RAILWAY_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "JARVIS/1.0",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _RAILWAY_GQL_URL,
            json={
                "query": query,
                "variables": {
                    "serviceId": settings.RAILWAY_SERVICE_ID,
                    "environmentId": settings.RAILWAY_ENV_ID or "",
                },
            },
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    edges = data.get("data", {}).get("deployments", {}).get("edges", [])
    if not edges:
        return {"deploy_status": "no_deployments"}

    latest = edges[0]["node"]
    return {
        "deploy_status": latest.get("status", "unknown"),
        "deploy_id": latest.get("id", ""),
        "deploy_created_at": latest.get("createdAt", ""),
    }


async def _get_quality_trend(days: int = 7) -> dict[str, Any]:
    """Load quality signals for the last N days and compute trends."""
    redis = await get_redis_client()
    daily_stats: list[dict] = []

    for i in range(days):
        date = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        raw = await redis.cache_get(f"{_KEY_QUALITY_SIGNALS}:{date}")
        if not raw:
            daily_stats.append({"date": date, "positive": 0, "negative": 0})
            continue

        try:
            signals = json.loads(raw)
            pos = sum(1 for s in signals if s.get("signal") == "positive")
            neg = sum(1 for s in signals if s.get("signal") == "negative")
            daily_stats.append({"date": date, "positive": pos, "negative": neg})
        except (json.JSONDecodeError, TypeError):
            daily_stats.append({"date": date, "positive": 0, "negative": 0})

    total_pos = sum(d["positive"] for d in daily_stats)
    total_neg = sum(d["negative"] for d in daily_stats)

    return {
        "period_days": days,
        "total_positive": total_pos,
        "total_negative": total_neg,
        "satisfaction_ratio": round(total_pos / max(total_pos + total_neg, 1) * 100, 1),
        "daily": list(reversed(daily_stats)),
    }


async def _get_resource_trend(days: int = 7) -> dict[str, Any]:
    """Load resource usage snapshots for the last N days."""
    redis = await get_redis_client()
    snapshots: list[dict] = []

    for i in range(days):
        date = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        raw = await redis.cache_get(f"{_KEY_RESOURCE_USAGE}:{date}")
        if raw:
            try:
                snap = json.loads(raw)
                snap["date"] = date
                snapshots.append(snap)
            except (json.JSONDecodeError, TypeError):
                continue

    return {
        "period_days": days,
        "snapshots_available": len(snapshots),
        "snapshots": list(reversed(snapshots)),
    }


async def _synthesize_report_narrative(report: dict[str, Any]) -> str:
    """Use Gemini to synthesize a human-readable narrative from report data."""
    # Build a compact summary for the LLM
    sections: list[str] = []

    tool_stats = report.get("tool_stats", {})
    if isinstance(tool_stats, dict) and not tool_stats.get("error"):
        sections.append(
            f"Tool Stats ({tool_stats.get('period_days', '?')}d): "
            f"{tool_stats.get('total_executions', 0)} executions, "
            f"{tool_stats.get('success_rate', '?')}% success rate. "
            f"Most used: {json.dumps(tool_stats.get('most_used', [])[:5])}. "
            f"Most failed: {json.dumps(tool_stats.get('most_failed', [])[:5])}. "
            f"Slowest: {json.dumps(tool_stats.get('slowest', [])[:5])}."
        )

    quality = report.get("quality_trend", {})
    if isinstance(quality, dict) and not quality.get("error"):
        sections.append(
            f"Quality: {quality.get('total_positive', 0)} positive, "
            f"{quality.get('total_negative', 0)} negative signals. "
            f"Satisfaction ratio: {quality.get('satisfaction_ratio', '?')}%."
        )

    gaps = report.get("capability_gaps", [])
    if isinstance(gaps, list) and gaps:
        gap_summary = "; ".join(g.get("gap", "") for g in gaps[:5])
        sections.append(f"Capability gaps: {gap_summary}")

    learning = report.get("learning_metrics", {})
    if isinstance(learning, dict) and not learning.get("error"):
        sections.append(f"Learning metrics: {json.dumps(learning)[:500]}")

    code_health = report.get("code_health", {})
    if isinstance(code_health, dict) and not code_health.get("error"):
        sections.append(f"Code health: {json.dumps(code_health)[:500]}")

    if not sections:
        return "Insufficient data to generate a narrative report."

    prompt = (
        "You are JARVIS's self-improvement system. Write a concise weekly report "
        "(3-5 paragraphs) summarising performance, trends, and recommendations. "
        "Be direct and actionable. Use Paul Bettany's JARVIS tone — dry, British, efficient.\n\n"
        "Data:\n" + "\n".join(sections)
    )

    try:
        llm = get_llm_client()
        response = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1500,
        )
        return response.get("content", "Report generation returned empty content.")
    except Exception as exc:
        return f"Narrative synthesis failed: {exc}"
