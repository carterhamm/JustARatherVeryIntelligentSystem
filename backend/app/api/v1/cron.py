"""Cron-triggered endpoints for JARVIS autonomous routines.

Secured with SERVICE_API_KEY -- only Railway cron or daemon processes
should call these endpoints.

Includes:
  - Morning routine (enhanced with focus stats, habits, travel time)
  - Research daemon cycle
  - Heartbeat (enhanced with urgency scoring, focus awareness, aggregation)
  - Focus session management
  - Engagement tracking status
"""

from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime
from typing import Any

import zoneinfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import log_audit
from app.core.dependencies import get_current_active_user_or_service, get_db
from app.db.redis import get_redis_client
from app.integrations.llm.factory import get_llm_client
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

logger = logging.getLogger("jarvis.cron")


async def require_service_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Only accept X-Service-Key for cron endpoints. Reject JWT."""
    service_key = request.headers.get("x-service-key")
    if not service_key:
        raise HTTPException(status_code=401, detail="Service key required")
    if not hmac.compare_digest(service_key, settings.SERVICE_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid service key")
    result = await db.execute(select(User).where(User.is_active.is_(True)).limit(1))
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=500, detail="No active owner")
    return owner

router = APIRouter(prefix="/cron", tags=["Cron"])

_MTN = zoneinfo.ZoneInfo("America/Denver")


async def _get_owner(db: AsyncSession) -> User:
    """Get the single owner user."""
    result = await db.execute(
        select(User).where(User.is_active.is_(True)).limit(1)
    )
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=500, detail="No active owner found")
    return owner


async def _gather_morning_data() -> dict[str, Any]:
    """Gather all data needed for the morning briefing."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    data: dict[str, Any] = {}

    now = datetime.now(tz=_MTN)
    data["date_time"] = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")

    # Weather
    weather_tool = registry.get("weather")
    if weather_tool:
        try:
            data["weather"] = await weather_tool.run(
                {"location": "Orem, Utah", "type": "current"},
            )
        except Exception as exc:
            logger.warning("Morning weather failed: %s", exc)
            data["weather"] = "Weather unavailable."

    # Forecast
    if weather_tool:
        try:
            data["forecast"] = await weather_tool.run(
                {"location": "Orem, Utah", "type": "forecast"},
            )
        except Exception as exc:
            data["forecast"] = ""

    # Calendar (via iMCP if available)
    cal_tool = registry.get("mac_events_fetch")
    if cal_tool:
        try:
            today = now.strftime("%Y-%m-%d")
            data["calendar"] = await cal_tool.run(
                {"start_date": f"{today}T00:00:00", "end_date": f"{today}T23:59:59"},
            )
        except Exception as exc:
            logger.warning("Morning calendar failed: %s", exc)
            data["calendar"] = ""

    # News headlines
    news_tool = registry.get("news")
    if news_tool:
        try:
            data["news"] = await news_tool.run(
                {"category": "technology", "limit": 3},
            )
        except Exception as exc:
            data["news"] = ""

    return data


_MORNING_PROMPT = """\
You are JARVIS composing a morning briefing for Mr. Stark. Write a spoken script (will be read aloud by TTS) that is:
- Natural, warm, British, Paul Bettany delivery
- 15-25 seconds when spoken (~40-70 words)
- Start with "Good morning, sir." then the time
- Include weather summary (temperature, conditions, what to wear if relevant)
- If there are calendar events, mention the first one or two briefly
- If there's interesting news, one sentence max
- End with something encouraging or a light Iron Man reference (vary it each day). \
  You can draw from suit lore: Model Prime's hexagonal scales, Bleeding Edge's R.T. node, \
  Mark 42's prehensile assembly, Mark 85 holding the Stones — keep it clever and brief
- Say "sir" lowercase, say "JARVIS" not "J.A.R.V.I.S."
- Do NOT use asterisks, markdown, or formatting — this is pure spoken text

Here is today's data:
{data}

Write ONLY the spoken script, nothing else."""


@router.post("/morning-routine")
async def morning_routine(
    request: Request,
    current_user: User = Depends(require_service_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute the JARVIS morning routine (enhanced).

    1. Gather weather, calendar, news, focus stats, overnight emails, reminders
    2. Compose enriched briefing script via Gemini
    3. Generate ElevenLabs audio
    4. Play on MacBook -> AirPlay to Apple TV
    5. Start music
    """
    from app.services.heartbeat import (
        gather_enhanced_morning_data,
        get_enhanced_morning_prompt,
    )

    logger.info("Morning routine triggered")
    log_audit("cron_morning_routine", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")

    # 1. Gather data -- try enhanced first, fall back to legacy
    owner = await _get_owner(db)
    owner_id = str(owner.id)

    try:
        data = await gather_enhanced_morning_data(owner_id, db)
        morning_prompt_template = get_enhanced_morning_prompt()
        logger.info("Enhanced morning data gathered: %s", list(data.keys()))
    except Exception as exc:
        logger.warning("Enhanced morning data failed (%s), using legacy", exc)
        data = await _gather_morning_data()
        morning_prompt_template = _MORNING_PROMPT
        logger.info("Legacy morning data gathered: %s", list(data.keys()))

    # 2. Generate briefing script via LLM
    llm = get_llm_client()
    prompt = morning_prompt_template.format(data="\n".join(f"{k}: {v}" for k, v in data.items()))

    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": "You are JARVIS, writing a morning briefing script."},
            {"role": "user", "content": prompt},
        ],
    )
    script = response["content"].strip()
    logger.info("Morning script: %s", script[:200])

    # 3. Generate ElevenLabs audio
    from app.integrations.elevenlabs import ElevenLabsClient

    audio_bytes = None
    try:
        async with ElevenLabsClient(
            api_key=settings.ELEVENLABS_API_KEY,
            default_voice_id=settings.ELEVENLABS_VOICE_ID,
        ) as tts:
            audio_bytes = await tts.synthesize(script, output_format="mp3_44100_128")
        logger.info("Morning audio generated: %d bytes", len(audio_bytes))
    except Exception as exc:
        logger.exception("Morning TTS failed: %s", exc)

    # 4. Play on MacBook via iMCP bridge → AirPlay to Apple TV
    results = {"script": script, "audio_size": len(audio_bytes) if audio_bytes else 0}

    if audio_bytes and settings.IMCP_BRIDGE_URL:
        try:
            import httpx
            import base64

            audio_b64 = base64.b64encode(audio_bytes).decode()

            # Send audio to iMCP bridge for playback
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{settings.IMCP_BRIDGE_URL}/play-audio",
                    headers={"Authorization": f"Bearer {settings.IMCP_BRIDGE_KEY}"},
                    json={
                        "audio_b64": audio_b64,
                        "format": "mp3",
                        "target": "apple_tv",
                    },
                )
                results["playback"] = resp.json() if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as exc:
            logger.warning("iMCP playback failed: %s", exc)
            results["playback"] = f"Failed: {exc}"

    # 5. Trigger music on MacBook → Apple TV
    if settings.IMCP_BRIDGE_URL:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.post(
                    f"{settings.IMCP_BRIDGE_URL}/run-shortcut",
                    headers={"Authorization": f"Bearer {settings.IMCP_BRIDGE_KEY}"},
                    json={
                        "shortcut_name": "JARVIS Morning Music",
                        "input": "Leave it in my Dreams by The Voidz",
                    },
                )
                results["music"] = resp.json() if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as exc:
            logger.warning("Music trigger failed: %s", exc)
            results["music"] = f"Failed: {exc}"

    # 6. Also store in chat history so JARVIS remembers the briefing
    try:
        owner = await _get_owner(db)
        redis = await get_redis_client()
        service = ChatService(db=db, redis=redis, llm_client=llm)
        chat_request = ChatRequest(
            message=f"[Morning Routine] I just woke up. Here's today's briefing you composed: {script}",
            model_provider="gemini",
            voice_enabled=False,
        )
        await service.chat(owner.id, chat_request)
    except Exception as exc:
        logger.warning("Failed to store morning briefing in chat: %s", exc)

    results["status"] = "ok"
    return results


@router.get("/morning-routine/config")
async def get_morning_config(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Get current morning routine configuration."""
    r = await get_redis_client()
    wake_time = await r.cache_get("jarvis:morning:wake_time") or "06:45"
    music = await r.cache_get("jarvis:morning:music") or "Leave it in my Dreams by The Voidz"
    enabled = await r.cache_get("jarvis:morning:enabled") or "true"

    return {
        "wake_time": wake_time,
        "music": music,
        "enabled": enabled == "true",
    }


@router.post("/morning-routine/config")
async def set_morning_config(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, str]:
    """Update morning routine configuration.

    JARVIS can call this when Mr. Stark says "wake me up at 7 tomorrow".
    """
    r = await get_redis_client()

    if "wake_time" in payload:
        await r.cache_set("jarvis:morning:wake_time", payload["wake_time"], ttl=86400 * 365)
    if "music" in payload:
        await r.cache_set("jarvis:morning:music", payload["music"], ttl=86400 * 365)
    if "enabled" in payload:
        await r.cache_set("jarvis:morning:enabled", str(payload["enabled"]).lower(), ttl=86400 * 365)

    return {"status": "updated"}


# ═══════════════════════════════════════════════════════════════════════════
# Research daemon
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/research-cycle")
async def research_cycle(
    request: Request,
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Execute one iteration of the JARVIS research daemon.

    Picks the next topic in rotation, runs web searches, summarises via
    Gemini, and stores findings in Redis with 7-day TTL.

    Meant to be called by a Railway cron service (e.g. every 4 hours).
    """
    from app.services.research_daemon import run_research_cycle

    logger.info("Research cycle triggered by user=%s", current_user.username)
    log_audit("cron_research_cycle", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")
    result = await run_research_cycle()
    return result


@router.get("/research-findings")
async def research_findings(
    topic: str = "",
    days: int = 3,
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return recent research findings, optionally filtered by topic."""
    from app.services.research_daemon import get_all_topic_names, get_research_summary

    summary = await get_research_summary(topic=topic, days=days)
    topics = await get_all_topic_names()

    return {
        "summary": summary,
        "available_topics": topics,
        "filter": {"topic": topic or "(all)", "days": days},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Heartbeat — proactive monitoring every 15 minutes
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# Reminder delivery — lightweight check every 5 minutes
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/check-reminders")
async def check_reminders_cron(
    request: Request,
    current_user: User = Depends(require_service_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deliver due reminders via iMessage (or call as fallback).

    Lightweight — no LLM scoring.  Reminders are user-requested and always
    delivered immediately, even during DND.  Runs every 5 minutes for
    precise timing.

    Protected by SERVICE_API_KEY — meant to be called by Railway cron.
    """
    from app.services.heartbeat import check_and_deliver_reminders

    logger.info("Reminder check triggered by user=%s", current_user.username)
    log_audit("cron_check_reminders", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")
    try:
        result = await check_and_deliver_reminders(db)
    except Exception as exc:
        logger.exception("Reminder check failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Reminder check error: {exc}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Heartbeat — proactive monitoring every 15 minutes
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/heartbeat")
async def heartbeat_cron(
    request: Request,
    current_user: User = Depends(require_service_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute a single JARVIS heartbeat cycle.

    Checks email, calendar, weather, reminders, and research findings.
    Contacts the owner via iMessage (work hours), Twilio call (off hours),
    or silently logs (nighttime DND).

    Protected by SERVICE_API_KEY — meant to be called by Railway cron
    every 15 minutes.
    """
    from app.services.heartbeat import run_heartbeat

    logger.info("Heartbeat triggered by user=%s", current_user.username)
    log_audit("cron_heartbeat", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")
    try:
        result = await run_heartbeat(db)
    except Exception as exc:
        logger.exception("Heartbeat failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Heartbeat error: {exc}")
    return result


@router.get("/heartbeat/status")
async def heartbeat_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return the latest heartbeat result, today's log, and focus session state."""
    from datetime import datetime as _dt
    from app.services.heartbeat import (
        get_contact_method,
        _MTN,
        _check_focus_session,
    )

    r = await get_redis_client()

    # Current contact method
    now = _dt.now(tz=_MTN)
    method = get_contact_method(now)

    # Last result
    last_raw = await r.cache_get("jarvis:heartbeat:last_result")
    last_result = json.loads(last_raw) if last_raw else None

    # Today's log
    today = now.strftime("%Y-%m-%d")
    log_raw = await r.cache_get(f"jarvis:heartbeat:log:{today}")
    today_log = json.loads(log_raw) if log_raw else []

    # Focus session state
    owner_id = str(current_user.id)
    focus = await _check_focus_session(owner_id, r)

    # Focus queue count
    queue_raw = await r.cache_get(f"jarvis:heartbeat:focus_queue:{owner_id}")
    queued_count = len(json.loads(queue_raw)) if queue_raw else 0

    # Today's urgency score distribution
    urgency_distribution: dict[str, int] = {}
    for entry in today_log:
        for cat, score in entry.get("urgency_scores", {}).items():
            urgency_distribution[cat] = max(
                urgency_distribution.get(cat, 0), score
            )

    return {
        "current_time": now.strftime("%I:%M %p %Z"),
        "current_contact_method": method,
        "last_heartbeat": last_result,
        "today_log": today_log,
        "today_run_count": len(today_log),
        "focus_session": focus,
        "queued_notifications": queued_count,
        "today_peak_urgency_by_category": urgency_distribution,
    }


# ===================================================================
# Focus session management
# ===================================================================


@router.post("/focus/start")
async def start_focus(
    payload: dict[str, Any],
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Start a focus session for the current user.

    Suppresses all heartbeat notifications except urgency 10 (emergencies).
    Suppressed notifications are queued and delivered when the session ends.

    Payload:
        duration_minutes (int): How long the session lasts (default: 60)
        label (str): Optional label like "deep work", "coding", "meeting"
    """
    from app.services.heartbeat import start_focus_session

    owner_id = str(current_user.id)
    duration = payload.get("duration_minutes", 60)
    label = payload.get("label", "")

    result = await start_focus_session(owner_id, duration, label)
    logger.info(
        "Focus session started: user=%s duration=%d label=%s",
        current_user.username, duration, label,
    )
    return result


@router.post("/focus/end")
async def end_focus(
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """End the current focus session and deliver queued notifications.

    Returns any notifications that were suppressed during the session.
    """
    from app.services.heartbeat import end_focus_session

    owner_id = str(current_user.id)
    result = await end_focus_session(owner_id)
    logger.info(
        "Focus session ended: user=%s status=%s queued=%d",
        current_user.username,
        result["status"],
        len(result.get("queued_notifications", [])),
    )
    return result


@router.get("/focus/status")
async def focus_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Check if a focus session is currently active."""
    from app.services.heartbeat import _check_focus_session, _MTN

    r = await get_redis_client()
    owner_id = str(current_user.id)

    session = await _check_focus_session(owner_id, r)

    # Check queue
    queue_raw = await r.cache_get(f"jarvis:heartbeat:focus_queue:{owner_id}")
    queued = json.loads(queue_raw) if queue_raw else []

    # Today's focus stats
    today = datetime.now(tz=_MTN).strftime("%Y-%m-%d")
    stats_raw = await r.cache_get(f"jarvis:focus:daily_stats:{owner_id}:{today}")
    today_stats = json.loads(stats_raw) if stats_raw else {
        "sessions": 0, "total_minutes": 0, "labels": [],
    }

    return {
        "active": session is not None,
        "session": session,
        "queued_notifications": len(queued),
        "today_stats": today_stats,
    }


# ===================================================================
# Engagement / learning metrics
# ===================================================================


@router.get("/heartbeat/engagement")
async def heartbeat_engagement(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return notification engagement statistics.

    Shows how the user interacts with different notification categories,
    enabling the urgency scoring to learn from patterns over time.
    """
    from app.services.heartbeat import _get_engagement_stats, _ENGAGEMENT_KEY_PREFIX

    r = await get_redis_client()
    owner_id = str(current_user.id)

    categories = ["email", "calendar", "weather", "reminders", "research"]
    stats_by_category: dict[str, Any] = {}

    for cat in categories:
        stats_by_category[cat] = await _get_engagement_stats(cat, r, owner_id)

    # Overall stats
    log_key = f"{_ENGAGEMENT_KEY_PREFIX}:{owner_id}:log"
    raw = await r.cache_get(log_key)
    total_entries = 0
    total_responded = 0
    if raw:
        entries = json.loads(raw)
        total_entries = len(entries)
        total_responded = sum(1 for e in entries if e.get("responded"))

    return {
        "by_category": stats_by_category,
        "overall": {
            "total_notifications": total_entries,
            "total_responded": total_responded,
            "response_rate": round(total_responded / total_entries, 2) if total_entries else 0,
        },
    }


@router.post("/heartbeat/engagement/record-response")
async def record_engagement_response(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, str]:
    """Record that the user responded to a recent notification.

    Call this when the user sends a message shortly after a heartbeat
    notification, so the system learns which notifications are valuable.
    """
    from app.services.heartbeat import record_user_response

    r = await get_redis_client()
    owner_id = str(current_user.id)
    await record_user_response(owner_id, r)
    return {"status": "recorded"}


# ═══════════════════════════════════════════════════════════════════════════
# MCP Discovery — weekly scan
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/mcp-scan")
async def mcp_scan(
    request: Request,
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Run a full MCP server discovery scan and cache the results.

    Searches GitHub for MCP servers across multiple queries, scores and ranks
    them, then stores the top 100 in Redis with a 24-hour TTL.

    Intended to be called weekly by a Railway cron job.  The scan respects
    GitHub's unauthenticated rate limit (10 req/min) so it takes 1–2 minutes.
    """
    from app.services.mcp_discovery import run_mcp_scan

    logger.info("MCP scan triggered by user=%s", current_user.username)
    log_audit("cron_mcp_scan", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")
    try:
        result = await run_mcp_scan()
    except Exception as exc:
        logger.exception("MCP scan failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"MCP scan error: {exc}")
    return result


@router.get("/mcp-scan/status")
async def mcp_scan_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return the status and summary of the latest MCP discovery scan."""
    from app.services.mcp_discovery import get_cached_scan

    r = await get_redis_client()
    last_scan_ts = await r.cache_get("jarvis:mcp:last_scan")

    cached = await get_cached_scan()
    if cached:
        return {
            "status": "available",
            "last_scan": last_scan_ts or cached.get("scanned_at"),
            "total_servers": cached.get("total_found", 0),
            "elapsed_seconds": cached.get("elapsed_seconds"),
            "top_servers": [
                {
                    "full_name": s.get("full_name"),
                    "stars": s.get("stars"),
                    "score": s.get("score"),
                    "capabilities": s.get("capabilities", []),
                    "description": (s.get("description") or "")[:80],
                }
                for s in cached.get("servers", [])[:10]
            ],
        }

    return {
        "status": "no_scan",
        "last_scan": last_scan_ts,
        "message": "No scan results cached. POST to /cron/mcp-scan to run one.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Self-healing daemon — automatic error detection and repair
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/self-heal")
async def self_heal(
    request: Request,
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Execute a single self-healing cycle.

    1. Health-check the live backend and Railway deployment
    2. Scan recent deploy logs for Python tracebacks / crash signatures
    3. If errors detected, dispatch Claude Code on Mac Mini to fix
    4. Notify owner via iMessage with detection/fix report

    Protected by SERVICE_API_KEY — meant to be called by Railway cron
    every 15 minutes.
    """
    from app.services.self_heal import run_self_heal

    logger.info("Self-heal triggered by user=%s", current_user.username)
    log_audit("cron_self_heal", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")
    try:
        result = await run_self_heal()
    except Exception as exc:
        logger.exception("Self-heal failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Self-heal error: {exc}")
    return result


@router.get("/self-heal/status")
async def self_heal_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return the latest self-heal result and today's log."""
    import json as _json
    from datetime import datetime as _dt

    r = await get_redis_client()
    now = _dt.now(tz=_MTN)

    # Last result
    last_raw = await r.cache_get("jarvis:self_heal:last_result")
    last_result = _json.loads(last_raw) if last_raw else None

    # Today's log
    today = now.strftime("%Y-%m-%d")
    log_raw = await r.cache_get(f"jarvis:self_heal:log:{today}")
    today_log = _json.loads(log_raw) if log_raw else []

    return {
        "current_time": now.strftime("%I:%M %p %Z"),
        "last_self_heal": last_result,
        "today_log": today_log,
        "today_run_count": len(today_log),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Continuous Learning — enhanced research + ingestion + dialogue
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/learning-cycle")
async def learning_cycle(
    request: Request,
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Execute a full continuous learning cycle.

    Runs the enhanced research pipeline:
    1. Standard research (fixed topic rotation) + auto-ingest into Qdrant/Neo4j
    2. Trending topic detection + research + ingestion
    3. Deep web scraping of article URLs for richer content
    4. Internal dialogue (dual-LLM debate) for deeper insights

    This replaces the basic research-cycle for more comprehensive learning.
    Intended to be called by a Railway cron service (e.g. every 2-4 hours).

    Protected by SERVICE_API_KEY.
    """
    from app.services.continuous_learning import run_learning_cycle

    logger.info("Learning cycle triggered by user=%s", current_user.username)
    log_audit("cron_learning_cycle", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")
    try:
        result = await run_learning_cycle(
            include_trending=True,
            include_deep_scrape=True,
            include_dialogue=True,
        )
    except Exception as exc:
        logger.exception("Learning cycle failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Learning cycle error: {exc}")
    return result


@router.post("/internal-dialogue")
async def internal_dialogue(
    request: Request,
    payload: dict[str, Any] = {},
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Run an internal dialogue session on the most recent research finding.

    JARVIS debates with a neutral analyst to extract deeper insights.
    Insights are automatically stored in the knowledge base.

    Optional payload:
        topic (str): specific topic to discuss
        summary (str): specific content to discuss
        rounds (int): number of debate rounds (default 3)

    Protected by SERVICE_API_KEY.
    """
    from app.services.internal_dialogue import run_dialogue_session

    logger.info("Internal dialogue triggered by user=%s", current_user.username)
    log_audit("cron_internal_dialogue", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")

    topic = payload.get("topic", "")
    summary = payload.get("summary", "")
    rounds = payload.get("rounds", 3)

    # If no topic/summary provided, find the latest research finding
    if not topic or not summary:
        try:
            r = await get_redis_client()
            from app.services.research_daemon import RESEARCH_TOPICS
            best_ts = ""
            for t in RESEARCH_TOPICS:
                raw = await r.cache_get(f"jarvis:research:latest:{t['name']}")
                if raw:
                    try:
                        finding = json.loads(raw)
                        ts = finding.get("timestamp", "")
                        if ts > best_ts:
                            best_ts = ts
                            topic = finding.get("label", t["label"])
                            summary = finding.get("summary", "")
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception as exc:
            logger.warning("Could not find latest finding: %s", exc)

    if not summary:
        return {"status": "no_content", "message": "No research findings available for dialogue."}

    try:
        result = await run_dialogue_session(
            topic=topic,
            summary=summary,
            rounds=rounds,
            use_local_llm=True,
        )

        # Auto-ingest insights into knowledge base
        insights = result.get("insights", [])
        if insights:
            from app.services.continuous_learning import ingest_research_finding
            insight_lines = [f"- [{i.get('category', 'general')}] {i['insight']}" for i in insights]
            await ingest_research_finding({
                "topic": f"dialogue_{topic.lower().replace(' ', '_')[:30]}",
                "label": f"Dialogue Insights: {topic}",
                "summary": f"# Dialogue Insights: {topic}\n\n" + "\n".join(insight_lines),
                "source": "internal_dialogue",
                "date": datetime.now(tz=_MTN).strftime("%Y-%m-%d"),
            })

    except Exception as exc:
        logger.exception("Internal dialogue failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Dialogue error: {exc}")

    return result


@router.get("/learning/status")
async def learning_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return JARVIS's continuous learning metrics and progress.

    Shows: total documents ingested, entities discovered, knowledge base size,
    today's learning activity, and last cycle details.
    """
    from app.services.continuous_learning import get_learning_metrics

    metrics = await get_learning_metrics()

    # Also get trending topics if available
    trending = []
    try:
        r = await get_redis_client()
        raw = await r.cache_get("jarvis:learning:trends")
        if raw:
            trending = json.loads(raw)
    except Exception:
        pass

    # Dialogue history count
    dialogue_count = 0
    try:
        r = await get_redis_client()
        raw = await r.cache_get("jarvis:learning:dialogue_count")
        dialogue_count = int(raw) if raw else 0
    except Exception:
        pass

    return {
        **metrics,
        "trending_topics": [
            {"name": t.get("name", ""), "label": t.get("label", ""), "relevance": t.get("relevance_score", 0)}
            for t in trending[:5]
        ],
        "dialogue_sessions_total": dialogue_count,
    }


@router.post("/learning/detect-trends")
async def detect_trends(
    request: Request,
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Detect trending topics relevant to Mr. Stark's interests.

    Searches the web for trending news in tech, science, and business,
    then scores each topic by relevance to configured interests.

    Protected by SERVICE_API_KEY.
    """
    from app.services.trend_detector import detect_trending_topics

    logger.info("Trend detection triggered by user=%s", current_user.username)
    try:
        topics = await detect_trending_topics(max_topics=5)
    except Exception as exc:
        logger.exception("Trend detection failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Trend detection error: {exc}")

    return {
        "status": "ok",
        "topics_found": len(topics),
        "topics": topics,
    }


@router.post("/ingest-feynman")
async def ingest_feynman(
    request: Request,
    payload: dict[str, Any] = {},
    current_user: User = Depends(require_service_key),
) -> dict[str, Any]:
    """Ingest The Feynman Lectures on Physics into the knowledge base.

    Optional payload:
        volume (int): 1, 2, or 3 to ingest a specific volume. Omit for all.

    Protected by SERVICE_API_KEY. Long-running — may take 30+ minutes.
    """
    from app.services.feynman_ingestion import ingest_feynman_lectures

    logger.info("Feynman ingestion triggered by user=%s", current_user.username)
    log_audit("cron_feynman_ingest", "triggered", user_id=str(current_user.id), ip=request.client.host if request.client else "")

    volumes = None
    if "volume" in payload:
        volumes = [int(payload["volume"])]

    try:
        result = await ingest_feynman_lectures(volumes=volumes)
    except Exception as exc:
        logger.exception("Feynman ingestion failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Feynman ingestion error: {exc}")
    return result


@router.get("/ingest-feynman/status")
async def feynman_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Check Feynman Lectures ingestion progress."""
    from app.services.feynman_ingestion import get_ingestion_status
    return await get_ingestion_status()
