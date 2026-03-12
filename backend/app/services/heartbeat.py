"""JARVIS Heartbeat — proactive monitoring that runs every 15 minutes.

Checks email, calendar, weather, reminders, and research findings, then
contacts the owner via the appropriate channel based on time-of-day rules:

  - Work hours → iMessage
  - Outside work hours (not night) → Twilio phone call
  - Nighttime (11 PM – 7 AM) → do not disturb, just log

Schedule rules (Mountain Time):
  - Until March 13 2026: Mon–Fri 8:00 AM – 4:30 PM
  - From March 13 2026:  Tue–Sat 10:00 AM – 6:30 PM (Sun+Mon off)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("jarvis.heartbeat")

_MTN = ZoneInfo("America/Denver")

# Owner phone in E.164
_OWNER_PHONE = "+17192136213"

# Schedule transition date
_SCHEDULE_SWITCH = date(2026, 3, 13)


# ═════════════════════════════════════════════════════════════════════════════
# Schedule logic
# ═════════════════════════════════════════════════════════════════════════════

def get_contact_method(now: Optional[datetime] = None) -> str:
    """Determine how to contact the owner based on current time.

    Returns one of: ``'text'``, ``'call'``, ``'dnd'``.
    """
    if now is None:
        now = datetime.now(tz=_MTN)
    else:
        now = now.astimezone(_MTN)

    hour = now.hour
    minute = now.minute
    current_time = hour * 60 + minute  # minutes since midnight
    weekday = now.weekday()  # 0=Mon, 6=Sun
    today = now.date()

    # DND: 11:00 PM (23:00) to 7:00 AM (07:00)
    if current_time >= 23 * 60 or current_time < 7 * 60:
        return "dnd"

    # Determine work hours based on schedule
    if today < _SCHEDULE_SWITCH:
        # Old schedule: Mon–Fri 8:00 AM – 4:30 PM
        is_work_day = weekday in (0, 1, 2, 3, 4)  # Mon–Fri
        work_start = 8 * 60       # 8:00 AM
        work_end = 16 * 60 + 30   # 4:30 PM
    else:
        # New schedule: Tue–Sat 10:00 AM – 6:30 PM
        is_work_day = weekday in (1, 2, 3, 4, 5)  # Tue–Sat
        work_start = 10 * 60      # 10:00 AM
        work_end = 18 * 60 + 30   # 6:30 PM

    if is_work_day and work_start <= current_time < work_end:
        return "text"

    return "call"


# ═════════════════════════════════════════════════════════════════════════════
# Data-gathering helpers
# ═════════════════════════════════════════════════════════════════════════════

async def _get_owner(db: AsyncSession):
    """Get the owner (first active user by created_at)."""
    from app.models.user import User

    result = await db.execute(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _check_unread_emails(owner_id: str) -> Optional[str]:
    """Check for unread emails via Gmail. Returns summary or None."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    tool = registry.get("read_email")
    if not tool:
        return None

    try:
        result = await tool.run(
            {"query": "is:unread is:important", "limit": 5},
            state={"user_id": owner_id},
        )
        if "not connected" in result.lower() or "no emails found" in result.lower():
            return None
        return result
    except Exception as exc:
        logger.warning("Heartbeat email check failed: %s", exc)
        return None


async def _check_calendar(owner_id: str) -> Optional[str]:
    """Check calendar events in the next 2 hours. Returns summary or None."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    tool = registry.get("list_calendar_events")
    if not tool:
        return None

    now = datetime.now(tz=_MTN)
    two_hours = now + timedelta(hours=2)

    try:
        result = await tool.run(
            {
                "start_date": now.isoformat(),
                "end_date": two_hours.isoformat(),
            },
            state={"user_id": owner_id},
        )
        if "not connected" in result.lower() or "no events found" in result.lower():
            return None
        return result
    except Exception as exc:
        logger.warning("Heartbeat calendar check failed: %s", exc)
        return None


async def _check_weather_alerts() -> Optional[str]:
    """Check for severe weather. Returns alert text or None."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    tool = registry.get("weather")
    if not tool:
        return None

    try:
        result = await tool.run(
            {"action": "current", "city": "Orem, Utah", "units": "imperial"},
        )
        if not result or "error" in result.lower():
            return None
        # Only flag if there's something extreme
        # Look for keywords that suggest severe conditions
        severe_keywords = [
            "tornado", "hurricane", "blizzard", "flood", "severe",
            "warning", "watch", "ice storm", "hail", "extreme",
        ]
        result_lower = result.lower()
        for keyword in severe_keywords:
            if keyword in result_lower:
                return result
        return None
    except Exception as exc:
        logger.warning("Heartbeat weather check failed: %s", exc)
        return None


async def _check_pending_reminders(db: AsyncSession, owner_id) -> Optional[str]:
    """Check for reminders due in the next 30 minutes. Returns summary or None."""
    from app.models.reminder import Reminder

    now = datetime.now(tz=timezone.utc)
    window = now + timedelta(minutes=30)

    try:
        result = await db.execute(
            select(Reminder)
            .where(
                Reminder.user_id == owner_id,
                Reminder.is_delivered.is_(False),
                Reminder.remind_at <= window,
            )
            .order_by(Reminder.remind_at.asc())
            .limit(10)
        )
        reminders = result.scalars().all()

        if not reminders:
            return None

        lines = []
        for r in reminders:
            remind_mtn = r.remind_at.astimezone(_MTN) if r.remind_at.tzinfo else r.remind_at
            lines.append(f"- {r.message} (due {remind_mtn.strftime('%I:%M %p')})")

            # Mark as delivered
            r.is_delivered = True
            r.delivered_at = now

        await db.commit()
        return "Pending reminders:\n" + "\n".join(lines)

    except Exception as exc:
        logger.warning("Heartbeat reminder check failed: %s", exc)
        return None


async def _check_research_findings() -> Optional[str]:
    """Check Redis for any new research findings. Returns text or None."""
    from app.db.redis import get_redis_client

    try:
        redis = await get_redis_client()
        findings = await redis.cache_get("jarvis:heartbeat:research_findings")
        if findings:
            # Clear after reading
            await redis.cache_delete("jarvis:heartbeat:research_findings")
            return f"Research findings:\n{findings}"
        return None
    except Exception as exc:
        logger.warning("Heartbeat research check failed: %s", exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Anti-spam / intelligence logic
# ═════════════════════════════════════════════════════════════════════════════

async def _is_noteworthy(
    findings: dict[str, str],
    redis_client,
) -> tuple[bool, str]:
    """Determine if findings are worth contacting the owner about.

    Returns (should_contact, reason).

    Rules:
    - Calendar event starting in <30 min → always contact
    - Severe weather alerts → always contact
    - Pending reminders → always contact
    - Unread important emails → contact, but not if we already notified
      about the same emails this hour
    - Research findings → always contact
    - First check of the day → contact with a summary even if routine
    """
    if not findings:
        return False, "nothing_found"

    # Always contact for these
    if "reminders" in findings:
        return True, "pending_reminders"
    if "weather" in findings:
        return True, "severe_weather"
    if "research" in findings:
        return True, "research_findings"

    # Calendar: check if event is starting within 30 min
    if "calendar" in findings:
        cal_text = findings["calendar"].lower()
        # The tool returns event times — if there are events, they're within
        # our 2-hour window. We flag as noteworthy.
        return True, "upcoming_calendar"

    # Email: check if we already notified about these recently
    if "email" in findings:
        email_hash = str(hash(findings["email"]))
        cache_key = "jarvis:heartbeat:last_email_hash"
        last_hash = await redis_client.cache_get(cache_key)
        if last_hash == email_hash:
            # Same emails as last check — skip unless first of day
            first_today = await _is_first_check_today(redis_client)
            if not first_today:
                return False, "duplicate_email_notification"
        # New emails — store hash and contact
        await redis_client.cache_set(cache_key, email_hash, ttl=3600)
        return True, "unread_emails"

    return False, "nothing_noteworthy"


async def _is_first_check_today(redis_client) -> bool:
    """Check if this is the first heartbeat of the day."""
    today_key = f"jarvis:heartbeat:date:{datetime.now(tz=_MTN).strftime('%Y-%m-%d')}"
    already_ran = await redis_client.cache_get(today_key)
    if already_ran:
        return False
    await redis_client.cache_set(today_key, "1", ttl=86400)
    return True


# ═════════════════════════════════════════════════════════════════════════════
# LLM summarization
# ═════════════════════════════════════════════════════════════════════════════

_SUMMARY_PROMPT = """\
You are JARVIS composing a brief proactive notification for Mr. Stark.
Be concise — 1-3 sentences max. British, dry, efficient. No filler.
If there are calendar events, lead with the most urgent.
If there are reminders, state them clearly.
Do NOT use markdown or formatting — this will be sent as a text message or spoken aloud.

Here is what the heartbeat found:
{findings}

Write ONLY the notification text."""


async def _summarize_findings(findings: dict[str, str]) -> str:
    """Use Gemini to compose a brief JARVIS-style notification."""
    from app.integrations.llm.factory import get_llm_client

    llm = get_llm_client("gemini")
    combined = "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in findings.items())
    prompt = _SUMMARY_PROMPT.format(findings=combined)

    try:
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "You are JARVIS, Paul Bettany style. Brief and efficient."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=200,
        )
        return response["content"].strip()
    except Exception as exc:
        logger.error("Heartbeat LLM summarization failed: %s", exc)
        # Fallback: just concatenate the raw findings
        return " | ".join(f"{k}: {v[:100]}" for k, v in findings.items())


# ═════════════════════════════════════════════════════════════════════════════
# Contact methods
# ═════════════════════════════════════════════════════════════════════════════

async def _send_text(message: str) -> dict[str, Any]:
    """Send an iMessage to the owner via Mac Mini agent."""
    from app.integrations.mac_mini import send_imessage, is_configured

    if not is_configured():
        logger.warning("Mac Mini agent not configured — cannot send heartbeat text")
        return {"success": False, "method": "text", "error": "Mac Mini not configured"}

    result = await send_imessage(to=_OWNER_PHONE, text=message)
    logger.info("Heartbeat iMessage sent: %s", result.get("success"))
    return {"success": result.get("success", False), "method": "text", "detail": result}


async def _make_call(message: str) -> dict[str, Any]:
    """Call the owner via Twilio with ElevenLabs TTS."""
    from app.config import settings
    from app.integrations.elevenlabs import ElevenLabsClient
    from app.integrations.twilio_client import call_user_with_audio

    import uuid as uuid_mod
    import redis.asyncio as aioredis

    # Generate TTS audio
    try:
        async with ElevenLabsClient(
            api_key=settings.ELEVENLABS_API_KEY,
            default_voice_id=settings.ELEVENLABS_VOICE_ID,
        ) as tts:
            audio_bytes = await tts.synthesize(
                message,
                model_id="eleven_turbo_v2_5",
                output_format="mp3_44100_128",
            )
    except Exception as exc:
        logger.error("Heartbeat TTS failed: %s", exc)
        return {"success": False, "method": "call", "error": f"TTS failed: {exc}"}

    # Cache audio in Redis (binary client)
    try:
        binary_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
        audio_id = uuid_mod.uuid4().hex
        audio_key = f"twilio_audio:{audio_id}"
        await binary_redis.set(audio_key, audio_bytes, ex=300)
        await binary_redis.aclose()
    except Exception as exc:
        logger.error("Heartbeat audio cache failed: %s", exc)
        return {"success": False, "method": "call", "error": f"Redis cache failed: {exc}"}

    # Place the call
    audio_url = f"https://app.malibupoint.dev/api/v1/twilio/audio/{audio_id}"
    sid = await call_user_with_audio(audio_url)

    if sid:
        logger.info("Heartbeat call placed: SID=%s", sid)
        return {"success": True, "method": "call", "call_sid": sid}
    else:
        logger.warning("Heartbeat call failed — Twilio not configured or error")
        return {"success": False, "method": "call", "error": "Twilio call failed"}


# ═════════════════════════════════════════════════════════════════════════════
# Main heartbeat entry point
# ═════════════════════════════════════════════════════════════════════════════

async def run_heartbeat(db: AsyncSession) -> dict[str, Any]:
    """Execute a single heartbeat cycle.

    1. Gather data from available sources
    2. Determine if anything is noteworthy
    3. Summarize via LLM
    4. Contact owner via appropriate channel (or log if DND)
    5. Store results in Redis

    Returns a status dict with findings, contact method, and delivery result.
    """
    from app.db.redis import get_redis_client

    logger.info("Heartbeat starting")
    now = datetime.now(tz=_MTN)
    results: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "status": "ok",
    }

    # 1. Get the owner
    owner = await _get_owner(db)
    if not owner:
        logger.error("Heartbeat: no active owner found")
        results["status"] = "error"
        results["error"] = "No active owner found"
        return results

    owner_id = str(owner.id)
    results["owner_id"] = owner_id

    # 2. Determine contact method
    method = get_contact_method(now)
    results["contact_method"] = method
    logger.info("Heartbeat contact method: %s (time: %s)", method, now.strftime("%I:%M %p %Z"))

    # 3. Gather data from all sources
    findings: dict[str, str] = {}

    email_data = await _check_unread_emails(owner_id)
    if email_data:
        findings["email"] = email_data

    calendar_data = await _check_calendar(owner_id)
    if calendar_data:
        findings["calendar"] = calendar_data

    weather_data = await _check_weather_alerts()
    if weather_data:
        findings["weather"] = weather_data

    reminder_data = await _check_pending_reminders(db, owner.id)
    if reminder_data:
        findings["reminders"] = reminder_data

    research_data = await _check_research_findings()
    if research_data:
        findings["research"] = research_data

    results["findings_count"] = len(findings)
    results["findings_types"] = list(findings.keys())
    logger.info("Heartbeat gathered %d findings: %s", len(findings), list(findings.keys()))

    # 4. Determine if noteworthy
    redis = await get_redis_client()
    noteworthy, reason = await _is_noteworthy(findings, redis)
    results["noteworthy"] = noteworthy
    results["reason"] = reason

    if not noteworthy:
        logger.info("Heartbeat: nothing noteworthy (%s) — skipping contact", reason)
        await _store_heartbeat_result(redis, results)
        return results

    # 5. Summarize via LLM
    summary = await _summarize_findings(findings)
    results["summary"] = summary
    logger.info("Heartbeat summary: %s", summary[:200])

    # 6. Deliver based on contact method
    if method == "dnd":
        logger.info("Heartbeat: DND mode — logging findings but not contacting")
        results["delivery"] = {"method": "dnd", "logged": True}
    elif method == "text":
        delivery = await _send_text(summary)
        results["delivery"] = delivery
    elif method == "call":
        delivery = await _make_call(summary)
        results["delivery"] = delivery
    else:
        logger.warning("Heartbeat: unknown contact method %s", method)
        results["delivery"] = {"method": method, "error": "unknown method"}

    # 7. Store results in Redis
    await _store_heartbeat_result(redis, results)

    logger.info("Heartbeat complete: method=%s noteworthy=%s reason=%s", method, noteworthy, reason)
    return results


async def _store_heartbeat_result(redis_client, results: dict[str, Any]) -> None:
    """Persist the latest heartbeat result to Redis."""
    try:
        await redis_client.cache_set(
            "jarvis:heartbeat:last_result",
            json.dumps(results, default=str),
            ttl=86400,  # 24 hours
        )
        # Also store a running log of today's heartbeats
        today = datetime.now(tz=_MTN).strftime("%Y-%m-%d")
        log_key = f"jarvis:heartbeat:log:{today}"
        existing = await redis_client.cache_get(log_key)
        entries = json.loads(existing) if existing else []
        entries.append({
            "time": results.get("timestamp", ""),
            "noteworthy": results.get("noteworthy", False),
            "reason": results.get("reason", ""),
            "method": results.get("contact_method", ""),
            "findings": results.get("findings_types", []),
        })
        await redis_client.cache_set(log_key, json.dumps(entries), ttl=86400 * 2)
    except Exception as exc:
        logger.warning("Failed to store heartbeat result in Redis: %s", exc)
