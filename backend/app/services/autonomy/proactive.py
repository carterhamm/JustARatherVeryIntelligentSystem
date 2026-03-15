"""Pillar 3: Proactive Features — anticipatory intelligence for JARVIS.

Detects opportunities to be useful before being asked: bonus learning
during idle periods, calendar conflict analysis, eureka alerts, and
system health monitoring.  Alerts are delivered via the smart delivery
engine, which respects time windows and daily limits.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.db.redis import get_redis_client
from app.db.session import async_session_factory
from app.integrations.llm.factory import get_llm_client
from app.services.autonomy.delivery import (
    DeliveryWindow,
    deliver_alert,
    get_delivery_window,
)

logger = logging.getLogger("jarvis.autonomy.proactive")

_MTN = ZoneInfo("America/Denver")

# ── Redis keys ───────────────────────────────────────────────────────────

_KEY_LOCK = "jarvis:autonomy:proactive:lock"
_KEY_IDLE_SINCE = "jarvis:autonomy:proactive:user_idle_since"
_KEY_CALENDAR_ANALYSIS = "jarvis:autonomy:proactive:calendar_analysis"  # :{date}
_KEY_LAST_CYCLE = "jarvis:autonomy:proactive:last_cycle"

# ── TTLs ─────────────────────────────────────────────────────────────────

_TTL_LOCK = 300          # 5 minutes
_TTL_IDLE = 7200         # 2 hours
_TTL_CALENDAR = 86400    # 24 hours
_TTL_LAST_CYCLE = 604800 # 7 days

# ── Waking hours (Mountain Time) ─────────────────────────────────────────

_WAKE_HOUR_START = 7
_WAKE_HOUR_END = 23
_IDLE_THRESHOLD_MIN = 30


# ═════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════


async def run_proactive_cycle() -> dict[str, Any]:
    """Execute a full proactive cycle.

    Phases:
        1. Detect user idle → trigger bonus learning if idle > 30 min
        2. Calendar conflict analysis (if Google Calendar connected)
        3. Generate proactive alerts (eureka, health, calendar)
        4. Smart delivery of any alerts via delivery engine

    Acquires a Redis lock to prevent overlapping runs.
    Returns a summary dict.
    """
    redis = await get_redis_client()

    # ── Acquire lock ─────────────────────────────────────────────
    existing = await redis.cache_get(_KEY_LOCK)
    if existing:
        logger.info("Proactive cycle already running — skipping")
        return {"status": "skipped", "reason": "lock_held"}

    await redis.cache_set(_KEY_LOCK, "running", ttl=_TTL_LOCK)
    cycle_start = _time.perf_counter()

    try:
        results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phases": {},
            "alerts_generated": 0,
            "alerts_delivered": 0,
            "errors": [],
        }

        # ── Phase 1: Idle detection + bonus learning ─────────────
        logger.info("Proactive phase 1: idle detection")
        try:
            is_idle = await _detect_user_idle()
            bonus_result: dict[str, Any] = {"user_idle": is_idle}
            if is_idle:
                bonus_result["learning"] = await _trigger_bonus_learning()
            results["phases"]["idle_detection"] = bonus_result
        except Exception as exc:
            logger.exception("Phase 1 (idle detection) failed: %s", exc)
            results["phases"]["idle_detection"] = {"status": "error", "error": str(exc)}
            results["errors"].append(f"idle_detection: {exc}")

        # ── Phase 2: Calendar conflict analysis ──────────────────
        logger.info("Proactive phase 2: calendar analysis")
        try:
            owner_id = await _get_owner_id()
            if owner_id:
                conflicts = await _analyze_calendar(owner_id)
                results["phases"]["calendar"] = {
                    "status": "ok",
                    "conflicts_found": len(conflicts),
                    "details": conflicts,
                }
            else:
                results["phases"]["calendar"] = {
                    "status": "skipped",
                    "reason": "no_owner_found",
                }
        except Exception as exc:
            logger.exception("Phase 2 (calendar) failed: %s", exc)
            results["phases"]["calendar"] = {"status": "error", "error": str(exc)}
            results["errors"].append(f"calendar: {exc}")

        # ── Phase 3: Generate proactive alerts ───────────────────
        logger.info("Proactive phase 3: alert generation")
        try:
            alerts = await _generate_proactive_alerts()
            results["phases"]["alerts"] = {
                "status": "ok",
                "count": len(alerts),
                "details": alerts,
            }
            results["alerts_generated"] = len(alerts)
        except Exception as exc:
            logger.exception("Phase 3 (alerts) failed: %s", exc)
            results["phases"]["alerts"] = {"status": "error", "error": str(exc)}
            results["errors"].append(f"alerts: {exc}")
            alerts = []

        # ── Phase 4: Smart delivery ──────────────────────────────
        logger.info("Proactive phase 4: delivery")
        delivered = 0
        for alert in alerts:
            try:
                delivery_result = await deliver_alert(
                    message=alert["message"],
                    priority=alert["priority"],
                )
                if delivery_result.get("delivered"):
                    delivered += 1
            except Exception as exc:
                logger.warning("Alert delivery failed: %s", exc)

        results["alerts_delivered"] = delivered

        # ── Finalise ─────────────────────────────────────────────
        elapsed_ms = int((_time.perf_counter() - cycle_start) * 1000)
        results["total_time_ms"] = elapsed_ms
        results["status"] = "ok" if not results["errors"] else "partial"

        await redis.cache_set(_KEY_LAST_CYCLE, json.dumps(results), ttl=_TTL_LAST_CYCLE)

        logger.info(
            "Proactive cycle complete — alerts=%d, delivered=%d, errors=%d, time=%dms",
            results["alerts_generated"],
            results["alerts_delivered"],
            len(results["errors"]),
            elapsed_ms,
        )

        return results

    finally:
        await redis.cache_delete(_KEY_LOCK)


async def update_user_activity() -> None:
    """Record that the user just interacted.

    Called by the chat service on each inbound message.
    Sets the idle-since timestamp with a 2-hour TTL.
    """
    try:
        redis = await get_redis_client()
        now = datetime.now(timezone.utc).isoformat()
        await redis.cache_set(_KEY_IDLE_SINCE, now, ttl=_TTL_IDLE)
    except Exception:
        logger.debug("Failed to update user activity timestamp", exc_info=True)


# ═════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════


async def _detect_user_idle() -> bool:
    """Return True if the user has been idle > 30 min during waking hours.

    Checks the ``user_idle_since`` key set by :func:`update_user_activity`.
    If the key is absent the user has been idle for over 2 hours (TTL expired)
    — we still treat that as idle during waking hours.
    """
    now_mtn = datetime.now(_MTN)

    # Outside waking hours — never trigger idle-based actions
    if not (_WAKE_HOUR_START <= now_mtn.hour < _WAKE_HOUR_END):
        return False

    try:
        redis = await get_redis_client()
        raw = await redis.cache_get(_KEY_IDLE_SINCE)

        if raw is None:
            # Key expired (>2h idle) or never set — treat as idle
            return True

        last_active = datetime.fromisoformat(raw)
        idle_minutes = (datetime.now(timezone.utc) - last_active).total_seconds() / 60
        return idle_minutes > _IDLE_THRESHOLD_MIN

    except Exception:
        logger.debug("Failed to check user idle state", exc_info=True)
        return False


async def _trigger_bonus_learning() -> dict[str, Any]:
    """Run an extra learning cycle while the user is idle.

    Checks that the learning lock is not already held before starting.
    Returns the cycle result or a skip reason.
    """
    try:
        redis = await get_redis_client()

        # Don't overlap with a running learning cycle
        lock_val = await redis.cache_get("jarvis:learning:cycle_lock")
        if lock_val:
            logger.info("Learning lock held — skipping bonus cycle")
            return {"status": "skipped", "reason": "learning_lock_held"}

        from app.services.continuous_learning import run_learning_cycle

        logger.info("User idle — triggering bonus learning cycle")
        result = await run_learning_cycle(
            include_trending=True,
            include_deep_scrape=False,  # lighter cycle during idle
            include_dialogue=True,
        )
        return {
            "status": result.get("status", "unknown"),
            "ingested": result.get("total_ingested", 0),
            "entities": result.get("total_entities", 0),
        }

    except Exception as exc:
        logger.exception("Bonus learning cycle failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def _analyze_calendar(owner_id: str) -> list[dict[str, Any]]:
    """Analyse today's and tomorrow's calendar for conflicts.

    Uses the calendar tool from the agent registry to fetch events,
    then sends them to Gemini for conflict/scheduling analysis.

    Results are cached per-day so we only run the analysis once.
    """
    today = datetime.now(_MTN).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(_MTN) + timedelta(days=1)).strftime("%Y-%m-%d")

    # Check cache — one analysis per calendar day
    redis = await get_redis_client()
    cache_key = f"{_KEY_CALENDAR_ANALYSIS}:{today}"
    cached = await redis.cache_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    # Fetch events via the calendar tool
    events_text = await _fetch_calendar_events(owner_id, today, tomorrow)
    if not events_text:
        return []

    # Ask Gemini to identify conflicts
    conflicts = await _llm_analyze_calendar(events_text, today, tomorrow)

    # Cache results for the day
    await redis.cache_set(cache_key, json.dumps(conflicts), ttl=_TTL_CALENDAR)

    return conflicts


async def _fetch_calendar_events(
    owner_id: str,
    start_date: str,
    end_date: str,
) -> str:
    """Fetch calendar events using the agent tool registry.

    Returns the raw text output from the calendar tool, or empty string
    if the tool is unavailable or Google Calendar is not connected.
    """
    try:
        from app.agents.tools import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get("list_calendar_events")
        if not tool:
            logger.debug("list_calendar_events tool not in registry")
            return ""

        # Build minimal agent state with the owner's user ID
        result = await tool.run(
            {"start_date": start_date, "end_date": end_date},
            state={"user_id": owner_id},
        )

        if not result or "not connected" in result.lower():
            logger.debug("Google Calendar not connected for owner")
            return ""

        return result

    except Exception as exc:
        logger.debug("Calendar event fetch failed: %s", exc)
        return ""


async def _llm_analyze_calendar(
    events_text: str,
    today: str,
    tomorrow: str,
) -> list[dict[str, Any]]:
    """Send calendar events to Gemini for conflict analysis.

    Returns a list of dicts with ``issue``, ``severity``, and ``suggestion`` keys.
    """
    try:
        llm = get_llm_client("gemini")

        prompt = (
            f"You are JARVIS, a personal AI assistant. Analyse these calendar events "
            f"for {today} and {tomorrow}.\n\n"
            f"{events_text}\n\n"
            "Identify:\n"
            "1. Overlapping or double-booked events\n"
            "2. Back-to-back meetings without breaks (need >=15 min gap)\n"
            "3. Overscheduled days (>6 hours of meetings)\n"
            "4. Early morning or late evening events that might need attention\n\n"
            "Return a JSON array of issues. Each issue:\n"
            '{"issue": "description", "severity": "high|medium|low", '
            '"suggestion": "what to do"}\n\n'
            "If no issues found, return an empty array: []\n"
            "Return ONLY the JSON array, no other text."
        )

        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "You are JARVIS. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )

        raw = response.get("content", "").strip()

        # Strip markdown fencing if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        conflicts = json.loads(raw)
        if not isinstance(conflicts, list):
            return []
        return conflicts

    except (json.JSONDecodeError, TypeError):
        logger.debug("Calendar LLM analysis returned non-JSON")
        return []
    except Exception as exc:
        logger.debug("Calendar LLM analysis failed: %s", exc)
        return []


async def _generate_proactive_alerts() -> list[dict[str, Any]]:
    """Scan for conditions worth alerting Mr. Stark about.

    Checks:
        - Calendar conflicts found (priority 6)
        - Learning system eureka insight (priority 9)
        - System health degraded (priority 8)

    Deduplicates against today's delivery log to avoid repeat alerts.
    """
    alerts: list[dict[str, Any]] = []
    already_sent = await _get_today_alert_messages()

    # ── Calendar conflicts ───────────────────────────────────────
    try:
        today = datetime.now(_MTN).strftime("%Y-%m-%d")
        redis = await get_redis_client()
        cache_key = f"{_KEY_CALENDAR_ANALYSIS}:{today}"
        cached = await redis.cache_get(cache_key)
        if cached:
            conflicts = json.loads(cached)
            high_conflicts = [c for c in conflicts if c.get("severity") == "high"]
            if high_conflicts:
                msg = (
                    f"Calendar alert: {len(high_conflicts)} scheduling "
                    f"{'conflict' if len(high_conflicts) == 1 else 'conflicts'} "
                    f"detected for today. "
                    f"{high_conflicts[0].get('issue', '')}"
                )
                if msg not in already_sent:
                    alerts.append({
                        "message": msg,
                        "priority": 6,
                        "category": "calendar",
                    })
    except Exception:
        logger.debug("Calendar alert check failed", exc_info=True)

    # ── Eureka insight from learning system ───────────────────────
    # ONLY alert for genuine eureka-category insights, NOT routine findings.
    # Mr. Stark's definition: eureka = paradigm-shifting physics discovery.
    # Routine insights (even good ones) should NOT generate notifications.
    # The dialogue system's _notify_findings already handles eureka alerts,
    # so this section is intentionally empty to avoid duplicate notifications.

    # ── System health ────────────────────────────────────────────
    try:
        health = await _quick_health_check()
        if health.get("status") == "degraded":
            issues = []
            if not health.get("qdrant_ok", True):
                issues.append("Qdrant unreachable")
            if not health.get("redis_ok", True):
                issues.append("Redis issues detected")
            if health.get("last_cycle_errors", 0) > 2:
                issues.append(f"{health['last_cycle_errors']} learning errors")

            if issues:
                msg = f"System health degraded: {', '.join(issues)}."
                if msg not in already_sent:
                    alerts.append({
                        "message": msg,
                        "priority": 8,
                        "category": "system_health",
                    })
    except Exception:
        logger.debug("Health alert check failed", exc_info=True)

    return alerts


async def _quick_health_check() -> dict[str, Any]:
    """Lightweight system health check for proactive alerting.

    Checks Redis connectivity, Qdrant accessibility, and recent
    learning cycle error counts.
    """
    result: dict[str, Any] = {"status": "ok"}

    try:
        redis = await get_redis_client()
        # Redis itself is reachable if we got here
        result["redis_ok"] = True

        # Check last learning cycle for errors
        last_cycle_raw = await redis.cache_get("jarvis:learning:last_cycle")
        if last_cycle_raw:
            last_cycle = json.loads(last_cycle_raw)
            error_count = len(last_cycle.get("errors", []))
            result["last_cycle_errors"] = error_count
            if error_count > 2:
                result["status"] = "degraded"
        else:
            result["last_cycle_errors"] = 0

    except Exception as exc:
        result["redis_ok"] = False
        result["status"] = "degraded"
        result["redis_error"] = str(exc)

    # Check Qdrant
    try:
        from app.db.qdrant import get_qdrant_store
        qdrant = get_qdrant_store()
        count = await qdrant.count()
        result["qdrant_ok"] = True
        result["qdrant_points"] = count
    except Exception as exc:
        result["qdrant_ok"] = False
        result["qdrant_error"] = str(exc)
        result["status"] = "degraded"

    return result


async def _get_today_alert_messages() -> set[str]:
    """Return the set of alert messages already delivered today.

    Reads from the delivery log to prevent duplicate alerts.
    """
    try:
        redis = await get_redis_client()
        today = datetime.now(_MTN).strftime("%Y-%m-%d")
        rkey = f"jarvis:autonomy:proactive:delivery_log:{today}"
        raw_entries = await redis.client.lrange(rkey, 0, -1)

        messages: set[str] = set()
        for raw in raw_entries:
            try:
                entry = json.loads(raw)
                msg = entry.get("message", "")
                if msg:
                    messages.add(msg)
            except (json.JSONDecodeError, TypeError):
                continue
        return messages

    except Exception:
        logger.debug("Failed to read today's delivery log", exc_info=True)
        return set()


async def _get_owner_id() -> str | None:
    """Fetch the owner (first active user) ID from the database.

    Returns the stringified UUID or None.
    """
    try:
        from sqlalchemy import select
        from app.models.user import User

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.is_active.is_(True)).limit(1)
            )
            owner = result.scalar_one_or_none()
            if owner:
                return str(owner.id)
    except Exception:
        logger.debug("Failed to fetch owner ID", exc_info=True)
    return None
