"""JARVIS Heartbeat — proactive monitoring that runs every 15 minutes.

Checks email, calendar, weather, reminders, and research findings, then
contacts the owner via the appropriate channel based on time-of-day rules:

  - Work hours -> iMessage
  - Outside work hours (not night) -> Twilio phone call
  - Nighttime (11 PM - 7 AM) -> do not disturb, just log

Schedule rules (Mountain Time):
  - Until March 13 2026: Mon-Fri 8:00 AM - 4:30 PM
  - From March 13 2026:  Tue-Sat 10:00 AM - 6:30 PM (Sun+Mon off)

Enhanced with:
  - Contextual urgency scoring via Gemini (1-10 per notification)
  - Focus session awareness (suppress non-emergency during focus)
  - Notification aggregation into batched digests
  - Engagement tracking / learning from user response patterns
  - Enhanced morning digest with habits, focus stats, travel time
"""

from __future__ import annotations

import json
import logging
import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger("jarvis.heartbeat")

_MTN = ZoneInfo("America/Denver")

# Schedule transition date
_SCHEDULE_SWITCH = date(2026, 3, 13)

# Urgency thresholds for notification delivery
_THRESHOLD_WORK_HOURS = 6       # Minimum score to notify during work
_THRESHOLD_OFF_HOURS = 8        # Minimum score outside work hours
_THRESHOLD_EMERGENCY = 10       # Always delivered, even in focus/DND
_THRESHOLD_FOCUS_SESSION = 10   # Only emergencies break through focus


# =============================================================================
# Schedule logic
# =============================================================================

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
        # Old schedule: Mon-Fri 8:00 AM - 4:30 PM
        is_work_day = weekday in (0, 1, 2, 3, 4)  # Mon-Fri
        work_start = 8 * 60       # 8:00 AM
        work_end = 16 * 60 + 30   # 4:30 PM
    else:
        # New schedule: Tue-Sat 10:00 AM - 6:30 PM
        is_work_day = weekday in (1, 2, 3, 4, 5)  # Tue-Sat
        work_start = 10 * 60      # 10:00 AM
        work_end = 18 * 60 + 30   # 6:30 PM

    if is_work_day and work_start <= current_time < work_end:
        return "text"

    return "call"


# =============================================================================
# Data-gathering helpers
# =============================================================================

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
    """Check for unread emails via Gmail + iCloud. Returns summary or None."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    sections: list[str] = []

    # --- Gmail ---
    gmail_tool = registry.get("read_email")
    if gmail_tool:
        try:
            gmail_result = await gmail_tool.run(
                {"query": "is:unread is:important", "limit": 5},
                state={"user_id": owner_id},
            )
            if gmail_result and "not connected" not in gmail_result.lower() and "no emails found" not in gmail_result.lower():
                sections.append(f"[Gmail]\n{gmail_result}")
        except Exception as exc:
            logger.warning("Heartbeat Gmail check failed: %s", exc)

    # --- iCloud Mail ---
    icloud_tool = registry.get("read_icloud_email")
    if icloud_tool:
        try:
            icloud_result = await icloud_tool.run(
                {"query": "unread", "limit": 5},
                state={"user_id": owner_id},
            )
            if icloud_result and "not connected" not in icloud_result.lower() and "no icloud emails found" not in icloud_result.lower():
                sections.append(f"[iCloud]\n{icloud_result}")
        except Exception as exc:
            logger.warning("Heartbeat iCloud email check failed: %s", exc)

    if not sections:
        return None
    return "\n\n".join(sections)


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
    """Report upcoming reminders for heartbeat digest (read-only).

    NOTE: This no longer marks reminders as delivered.  Delivery is handled
    by the dedicated ``check_and_deliver_reminders()`` cron (every 5 min).
    The heartbeat just includes upcoming reminder info in its findings so
    the urgency scorer has the full picture.
    """
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

        return "Pending reminders:\n" + "\n".join(lines)

    except Exception as exc:
        logger.warning("Heartbeat reminder check failed: %s", exc)
        return None


async def check_and_deliver_reminders(db: AsyncSession) -> dict[str, Any]:
    """Lightweight reminder delivery — runs every 5 minutes via dedicated cron.

    Queries due reminders and delivers immediately via iMessage (or call as
    fallback).  No LLM urgency scoring — reminders are always delivered
    because the user explicitly asked for them.

    Marks ``is_delivered`` only AFTER a successful send so nothing is lost
    silently.  Reminders fire even during DND since the user set them
    intentionally.
    """
    from app.models.reminder import Reminder

    now = datetime.now(tz=timezone.utc)
    results: dict[str, Any] = {"timestamp": now.isoformat(), "delivered": [], "failed": []}

    owner = await _get_owner(db)
    if not owner:
        results["status"] = "error"
        results["error"] = "No active owner"
        return results

    # Query reminders that are due (remind_at <= now) and not yet delivered
    stmt = (
        select(Reminder)
        .where(
            Reminder.user_id == owner.id,
            Reminder.is_delivered.is_(False),
            Reminder.remind_at <= now,
        )
        .order_by(Reminder.remind_at.asc())
        .limit(10)
    )
    rows = await db.execute(stmt)
    reminders = rows.scalars().all()

    if not reminders:
        results["status"] = "no_reminders_due"
        return results

    method = get_contact_method()

    for reminder in reminders:
        remind_mtn = (
            reminder.remind_at.astimezone(_MTN)
            if reminder.remind_at.tzinfo
            else reminder.remind_at
        )
        text = f"Reminder: {reminder.message} (due {remind_mtn.strftime('%I:%M %p')})"

        sent = False
        try:
            # Always try iMessage first — reminders are user-requested,
            # deliver even in DND / off-hours
            delivery = await _send_text(text)
            sent = delivery.get("success", False)

            # If iMessage failed and we're in call hours, try call
            if not sent and method == "call":
                delivery = await _make_call(text)
                sent = delivery.get("success", False)
        except Exception as exc:
            logger.error("Reminder delivery failed for '%s': %s", reminder.message, exc)

        if sent:
            reminder.is_delivered = True
            reminder.delivered_at = now
            results["delivered"].append(reminder.message)
            logger.info("Reminder delivered: %s", reminder.message)
        else:
            results["failed"].append(reminder.message)
            logger.warning("Reminder delivery failed: %s", reminder.message)

    await db.commit()
    results["status"] = "ok"
    results["total_due"] = len(reminders)
    return results


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


# =============================================================================
# Focus session awareness
# =============================================================================

async def _check_focus_session(owner_id: str, redis_client) -> Optional[dict[str, Any]]:
    """Check if the owner is in an active focus session.

    Returns the focus session data dict if active, None otherwise.

    Redis key pattern: ``focus_session:{user_id}:active``
    Expected value: JSON with keys ``started_at``, ``duration_minutes``,
    ``label`` (optional), ``suppress_until`` (ISO timestamp).
    """
    key = f"focus_session:{owner_id}:active"
    raw = await redis_client.cache_get(key)
    if not raw:
        return None

    try:
        session = json.loads(raw)
        # Check if the session has expired based on suppress_until
        suppress_until = session.get("suppress_until")
        if suppress_until:
            end_time = datetime.fromisoformat(suppress_until)
            if datetime.now(tz=_MTN) > end_time:
                # Session expired, clean it up
                await redis_client.cache_delete(key)
                logger.info("Focus session expired, cleaned up for user %s", owner_id)
                return None
        return session
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Invalid focus session data: %s", exc)
        return None


async def _queue_suppressed_notification(
    owner_id: str,
    redis_client,
    scored_items: list[dict[str, Any]],
) -> None:
    """Queue notifications that were suppressed during a focus session.

    These will be delivered in a batch when the focus session ends or at
    the next heartbeat after it expires.
    """
    queue_key = f"jarvis:heartbeat:focus_queue:{owner_id}"
    try:
        existing_raw = await redis_client.cache_get(queue_key)
        existing = json.loads(existing_raw) if existing_raw else []
        for item in scored_items:
            existing.append({
                "category": item["category"],
                "content": item["content"],
                "urgency": item["urgency"],
                "queued_at": datetime.now(tz=_MTN).isoformat(),
            })
        await redis_client.cache_set(
            queue_key,
            json.dumps(existing, default=str),
            ttl=86400,  # Keep for 24h max
        )
        logger.info(
            "Queued %d suppressed notifications for user %s (total in queue: %d)",
            len(scored_items), owner_id, len(existing),
        )
    except Exception as exc:
        logger.warning("Failed to queue suppressed notifications: %s", exc)


async def _drain_focus_queue(owner_id: str, redis_client) -> list[dict[str, Any]]:
    """Retrieve and clear any queued notifications from a past focus session.

    Returns list of queued items (may be empty).
    """
    queue_key = f"jarvis:heartbeat:focus_queue:{owner_id}"
    try:
        raw = await redis_client.cache_get(queue_key)
        if not raw:
            return []
        items = json.loads(raw)
        await redis_client.cache_delete(queue_key)
        logger.info("Drained %d queued focus-session notifications for user %s", len(items), owner_id)
        return items
    except Exception as exc:
        logger.warning("Failed to drain focus queue: %s", exc)
        return []


# =============================================================================
# Contextual urgency scoring (Gemini-powered)
# =============================================================================

_URGENCY_PROMPT = """\
You are JARVIS scoring notification urgency for Mr. Stark.

Current context:
- Current time: {current_time}
- Day of week: {day_of_week}
- Contact method: {contact_method} (text = work hours, call = off hours, dnd = nighttime)
- Focus session active: {focus_active}
- Already notified today about: {already_notified}

Score each notification below from 1 to 10:
- 1-3: Low priority (newsletters, FYI items, routine updates)
- 4-5: Moderate (non-urgent emails, events >1hr away)
- 6-7: Important (meeting in <45 min, emails from known contacts)
- 8-9: High priority (meeting in <15 min, urgent emails, weather warnings)
- 10: Emergency (severe weather danger, critical system alerts, imminent deadlines)

Consider:
- Time sensitivity: meeting in 5 min = 10, meeting in 2 hours = 4
- Sender importance: boss/family = high, newsletter = low
- Deduplication: if already notified about similar content today, lower score
- Time appropriateness: research findings at 2 AM = 2, urgent reminder at 2 AM = 9

Notifications to score:
{notifications}

Respond with ONLY a valid JSON array. Each element must have:
{{"category": "<category_name>", "urgency": <1-10>, "reason": "<brief explanation>"}}

Example: [{{"category": "calendar", "urgency": 8, "reason": "Meeting with client in 20 minutes"}}]"""


async def score_notification_urgency(
    findings: dict[str, str],
    contact_method: str,
    redis_client,
    owner_id: str,
    focus_session: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """Use Gemini to score each finding 1-10 on urgency.

    Returns a list of dicts with keys: category, content, urgency, reason.
    Falls back to heuristic scoring if the LLM call fails.
    """
    from app.integrations.llm.factory import get_llm_client

    if not findings:
        return []

    now = datetime.now(tz=_MTN)

    # Gather what we already notified about today for dedup context
    today = now.strftime("%Y-%m-%d")
    log_key = f"jarvis:heartbeat:log:{today}"
    log_raw = await redis_client.cache_get(log_key)
    today_log = json.loads(log_raw) if log_raw else []
    already_notified = set()
    for entry in today_log:
        if entry.get("noteworthy"):
            already_notified.update(entry.get("findings", []))

    # Build the notifications section for the prompt
    notification_lines = []
    for category, content in findings.items():
        # Truncate long content to keep prompt manageable
        truncated = content[:500] if len(content) > 500 else content
        notification_lines.append(f"[{category.upper()}]\n{truncated}")

    prompt = _URGENCY_PROMPT.format(
        current_time=now.strftime("%I:%M %p %Z"),
        day_of_week=now.strftime("%A"),
        contact_method=contact_method,
        focus_active="Yes" if focus_session else "No",
        already_notified=", ".join(already_notified) if already_notified else "nothing yet",
        notifications="\n\n".join(notification_lines),
    )

    try:
        llm = get_llm_client("gemini")
        response = await llm.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an urgency-scoring system. Return ONLY valid JSON. "
                        "No markdown, no explanation, just the JSON array."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )

        raw_content = response["content"].strip()
        # Strip markdown fences if present
        if raw_content.startswith("```"):
            raw_content = raw_content.split("\n", 1)[-1]
            if raw_content.endswith("```"):
                raw_content = raw_content[:-3].strip()

        scored = json.loads(raw_content)

        # Merge content back in and validate scores
        result = []
        for item in scored:
            cat = item.get("category", "").lower()
            urgency = min(max(int(item.get("urgency", 5)), 1), 10)
            # Apply engagement-based adjustment
            adjusted = await _adjust_urgency_from_engagement(
                cat, urgency, redis_client, owner_id,
            )
            result.append({
                "category": cat,
                "content": findings.get(cat, ""),
                "urgency": adjusted,
                "reason": item.get("reason", ""),
                "raw_urgency": urgency,
            })

        # Handle categories the LLM may have missed
        scored_categories = {item["category"] for item in result}
        for cat, content in findings.items():
            if cat not in scored_categories:
                fallback_score = _heuristic_urgency(cat, content, contact_method)
                result.append({
                    "category": cat,
                    "content": content,
                    "urgency": fallback_score,
                    "reason": "scored via heuristic fallback",
                    "raw_urgency": fallback_score,
                })

        logger.info(
            "Urgency scores: %s",
            {item["category"]: item["urgency"] for item in result},
        )
        return result

    except Exception as exc:
        logger.warning("LLM urgency scoring failed (%s), using heuristics", exc)
        return _heuristic_score_all(findings, contact_method)


def _heuristic_urgency(category: str, content: str, contact_method: str) -> int:
    """Fallback urgency scoring without LLM. Uses simple rules."""
    content_lower = content.lower()

    if category == "reminders":
        return 9  # Reminders the user explicitly set are always important

    if category == "weather":
        if any(kw in content_lower for kw in ("tornado", "hurricane", "extreme")):
            return 10
        return 8  # Severe weather already filtered by _check_weather_alerts

    if category == "calendar":
        # Look for time indicators suggesting imminence
        for phrase in ("in 5 min", "in 10 min", "in 15 min", "starts now", "starting soon"):
            if phrase in content_lower:
                return 9
        return 7  # Calendar events within 2hr window

    if category == "email":
        # Check for high-priority signals
        if any(kw in content_lower for kw in ("urgent", "asap", "critical", "emergency")):
            return 8
        return 5

    if category == "research":
        return 4  # Research is informational, rarely urgent

    return 5  # Default moderate


def _heuristic_score_all(
    findings: dict[str, str],
    contact_method: str,
) -> list[dict[str, Any]]:
    """Score all findings with heuristics (LLM fallback)."""
    result = []
    for cat, content in findings.items():
        score = _heuristic_urgency(cat, content, contact_method)
        result.append({
            "category": cat,
            "content": content,
            "urgency": score,
            "reason": "heuristic fallback",
            "raw_urgency": score,
        })
    return result


# =============================================================================
# Engagement tracking / learning from patterns
# =============================================================================

_ENGAGEMENT_KEY_PREFIX = "jarvis:heartbeat:engagement"
_ENGAGEMENT_TTL = 86400 * 30  # 30 days of history


async def track_notification_sent(
    category: str,
    urgency: int,
    redis_client,
    owner_id: str,
) -> None:
    """Record that a notification was sent. Called when we deliver a message.

    Stores: timestamp, category, urgency, and initially responded=false.
    The response tracker updates ``responded`` when the user interacts.
    """
    key = f"{_ENGAGEMENT_KEY_PREFIX}:{owner_id}:log"
    now = datetime.now(tz=_MTN)
    entry = {
        "id": hashlib.md5(f"{category}:{now.isoformat()}".encode()).hexdigest()[:12],
        "category": category,
        "urgency": urgency,
        "sent_at": now.isoformat(),
        "responded": False,
        "response_time_seconds": None,
    }

    try:
        raw = await redis_client.cache_get(key)
        log_entries = json.loads(raw) if raw else []
        log_entries.append(entry)
        # Keep only last 200 entries to avoid unbounded growth
        if len(log_entries) > 200:
            log_entries = log_entries[-200:]
        await redis_client.cache_set(key, json.dumps(log_entries), ttl=_ENGAGEMENT_TTL)
    except Exception as exc:
        logger.warning("Failed to track notification engagement: %s", exc)


async def record_user_response(
    owner_id: str,
    redis_client,
) -> None:
    """Mark the most recent unresponded notification as responded.

    Call this from the chat service when the user sends a message shortly
    after receiving a heartbeat notification (e.g., within 30 minutes).
    """
    key = f"{_ENGAGEMENT_KEY_PREFIX}:{owner_id}:log"
    now = datetime.now(tz=_MTN)

    try:
        raw = await redis_client.cache_get(key)
        if not raw:
            return
        entries = json.loads(raw)

        # Find the most recent unresponded entry sent in the last 30 min
        for entry in reversed(entries):
            if entry.get("responded"):
                continue
            sent_at = datetime.fromisoformat(entry["sent_at"])
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=_MTN)
            delta = (now - sent_at).total_seconds()
            if 0 < delta < 1800:  # Within 30 minutes
                entry["responded"] = True
                entry["response_time_seconds"] = int(delta)
                break

        await redis_client.cache_set(key, json.dumps(entries), ttl=_ENGAGEMENT_TTL)
    except Exception as exc:
        logger.warning("Failed to record user response: %s", exc)


async def _get_engagement_stats(
    category: str,
    redis_client,
    owner_id: str,
) -> dict[str, Any]:
    """Get engagement statistics for a notification category.

    Returns dict with response_rate, avg_response_time, and sample_size.
    """
    key = f"{_ENGAGEMENT_KEY_PREFIX}:{owner_id}:log"

    try:
        raw = await redis_client.cache_get(key)
        if not raw:
            return {"response_rate": 0.5, "avg_response_time": None, "sample_size": 0}

        entries = json.loads(raw)
        cat_entries = [e for e in entries if e.get("category") == category]

        if not cat_entries:
            return {"response_rate": 0.5, "avg_response_time": None, "sample_size": 0}

        responded = [e for e in cat_entries if e.get("responded")]
        response_rate = len(responded) / len(cat_entries) if cat_entries else 0.5
        avg_time = None
        if responded:
            times = [e["response_time_seconds"] for e in responded if e.get("response_time_seconds")]
            avg_time = sum(times) / len(times) if times else None

        return {
            "response_rate": round(response_rate, 2),
            "avg_response_time": round(avg_time) if avg_time else None,
            "sample_size": len(cat_entries),
        }
    except Exception as exc:
        logger.warning("Failed to get engagement stats: %s", exc)
        return {"response_rate": 0.5, "avg_response_time": None, "sample_size": 0}


async def _adjust_urgency_from_engagement(
    category: str,
    base_urgency: int,
    redis_client,
    owner_id: str,
) -> int:
    """Adjust urgency score based on historical engagement patterns.

    If the user consistently ignores a category, lower its urgency.
    If the user consistently responds quickly, maintain or boost it.
    Requires at least 5 data points before adjusting.
    """
    stats = await _get_engagement_stats(category, redis_client, owner_id)

    if stats["sample_size"] < 5:
        # Not enough data to adjust
        return base_urgency

    rate = stats["response_rate"]

    # High engagement (>70% response rate) -> slight boost (+1, max 10)
    if rate > 0.7:
        return min(base_urgency + 1, 10)

    # Low engagement (<20% response rate) -> lower score (-2, min 1)
    if rate < 0.2:
        return max(base_urgency - 2, 1)

    # Moderate-low engagement (<40%) -> slight decrease (-1)
    if rate < 0.4:
        return max(base_urgency - 1, 1)

    return base_urgency


# =============================================================================
# Anti-spam / intelligence logic (enhanced)
# =============================================================================

async def _is_noteworthy(
    findings: dict[str, str],
    redis_client,
) -> tuple[bool, str]:
    """Determine if findings are worth contacting the owner about.

    Returns (should_contact, reason).

    Rules:
    - Calendar event starting in <30 min -> always contact
    - Severe weather alerts -> always contact
    - Pending reminders -> always contact
    - Unread important emails -> contact, but not if we already notified
      about the same emails this hour
    - Research findings -> always contact
    - First check of the day -> contact with a summary even if routine
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
        # The tool returns event times -- if there are events, they're within
        # our 2-hour window. We flag as noteworthy.
        return True, "upcoming_calendar"

    # Email: check if we already notified about these recently
    if "email" in findings:
        email_hash = str(hash(findings["email"]))
        cache_key = "jarvis:heartbeat:last_email_hash"
        last_hash = await redis_client.cache_get(cache_key)
        if last_hash == email_hash:
            # Same emails as last check -- skip unless first of day
            first_today = await _is_first_check_today(redis_client)
            if not first_today:
                return False, "duplicate_email_notification"
        # New emails -- store hash and contact
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


# =============================================================================
# Notification aggregation
# =============================================================================

_DIGEST_PROMPT = """\
You are JARVIS composing a batched notification digest for Mr. Stark.
Be concise. British, dry, efficient. No filler. No markdown or formatting.
This will be sent as a text message or spoken aloud.

Rules:
- If there is 1 item, write 1-2 sentences.
- If there are multiple items, open with the count and list them as a brief numbered list.
  Example: "Three items of note, sir. 1) Meeting with Nexus AI in 45 minutes. 2) Spencer messaged about the Wagevo project. 3) BYU plays tonight at 7."
- Lead with the MOST urgent item (highest urgency score).
- Keep each item to one sentence max.
- Do NOT use asterisks, markdown, bullet points with dashes, or formatting.
- Use numbered items (1, 2, 3) for multiple items.
- Say "sir" not "Mr. Stark" (unless it's the morning greeting).

Here are the items to include, ordered by urgency (highest first):
{items}

Write ONLY the notification text."""


async def _compose_aggregated_digest(
    scored_items: list[dict[str, Any]],
) -> str:
    """Compose a single aggregated notification from multiple scored items.

    Uses Gemini to create a natural batched digest rather than sending
    individual notifications.
    """
    from app.integrations.llm.factory import get_llm_client

    # Sort by urgency descending
    sorted_items = sorted(scored_items, key=lambda x: x["urgency"], reverse=True)

    items_text = []
    for i, item in enumerate(sorted_items, 1):
        items_text.append(
            f"{i}. [{item['category'].upper()}] (urgency: {item['urgency']}/10)\n"
            f"   {item['content'][:300]}\n"
            f"   Reason: {item.get('reason', 'N/A')}"
        )

    prompt = _DIGEST_PROMPT.format(items="\n\n".join(items_text))

    try:
        llm = get_llm_client("gemini")
        response = await llm.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are JARVIS, Paul Bettany style. Brief and efficient.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=300,
        )
        return response["content"].strip()
    except Exception as exc:
        logger.error("Digest composition failed: %s", exc)
        # Fallback: simple concatenation
        lines = []
        for item in sorted_items:
            lines.append(f"{item['category']}: {item['content'][:100]}")
        return " | ".join(lines)


# =============================================================================
# LLM summarization (legacy, kept for backward compat)
# =============================================================================

_SUMMARY_PROMPT = """\
You are JARVIS composing a brief proactive notification for Mr. Stark.
Be concise -- 1-3 sentences max. British, dry, efficient. No filler.
If there are calendar events, lead with the most urgent.
If there are reminders, state them clearly.
Do NOT use markdown or formatting -- this will be sent as a text message or spoken aloud.

Here is what the heartbeat found:
{findings}

Write ONLY the notification text."""


async def _summarize_findings(findings: dict[str, str]) -> str:
    """Use Gemini to compose a brief JARVIS-style notification.

    Legacy path: used when urgency scoring is not available.
    The new path uses ``_compose_aggregated_digest`` instead.
    """
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


# =============================================================================
# Contact methods
# =============================================================================

async def _send_text(message: str) -> dict[str, Any]:
    """Send an iMessage to the owner via Mac Mini agent."""
    from app.integrations.mac_mini import send_imessage, is_configured

    if not is_configured():
        logger.warning("Mac Mini agent not configured -- cannot send heartbeat text")
        return {"success": False, "method": "text", "error": "Mac Mini not configured"}

    result = await send_imessage(to=settings.OWNER_PHONE, text=message)
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
        logger.warning("Heartbeat call failed -- Twilio not configured or error")
        return {"success": False, "method": "call", "error": "Twilio call failed"}


# =============================================================================
# Enhanced morning digest
# =============================================================================

_ENHANCED_MORNING_PROMPT = """\
You are JARVIS composing an enhanced morning briefing for Mr. Stark.
Write a spoken script (will be read aloud by TTS) that is:
- Natural, warm, British, Paul Bettany delivery
- 30-50 seconds when spoken (~80-130 words)
- Start with "Good morning, sir." then the time
- Include weather summary with outfit/activity suggestion if relevant
  (e.g. "Might want a jacket — highs only reaching 45 today")
- Calendar preview: list today's events with any travel time notes
- If there are overnight emails, mention the most important 1-2 briefly
- If there are focus session stats from yesterday, mention total focus time
- If there are habit completions from yesterday, one brief mention
- End with something encouraging or a light Iron Man reference (vary daily)
- Say "sir" lowercase, say "JARVIS" not "J.A.R.V.I.S."
- Do NOT use asterisks, markdown, or formatting — pure spoken text

Here is today's data:
{data}

Write ONLY the spoken script, nothing else."""


async def gather_enhanced_morning_data(owner_id: str, db: AsyncSession) -> dict[str, Any]:
    """Gather enriched data for the enhanced morning briefing.

    Supplements the standard morning data with:
    - Yesterday's focus session statistics
    - Overnight important emails
    - Today's full calendar (with travel time notes)
    - Weather-based suggestions
    """
    from app.agents.tools import get_tool_registry
    from app.db.redis import get_redis_client

    registry = get_tool_registry()
    redis = await get_redis_client()
    now = datetime.now(tz=_MTN)
    data: dict[str, Any] = {}

    data["date_time"] = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")

    # --- Weather (current + forecast for outfit suggestion) ---
    weather_tool = registry.get("weather")
    if weather_tool:
        try:
            current = await weather_tool.run(
                {"action": "current", "city": "Orem, Utah", "units": "imperial"},
            )
            data["weather_current"] = current
        except Exception as exc:
            logger.warning("Morning weather failed: %s", exc)
            data["weather_current"] = "Weather unavailable."

        try:
            forecast = await weather_tool.run(
                {"action": "forecast", "city": "Orem, Utah", "units": "imperial"},
            )
            data["weather_forecast"] = forecast
        except Exception as exc:
            data["weather_forecast"] = ""

    # --- Today's full calendar ---
    cal_tool = registry.get("list_calendar_events")
    if cal_tool:
        try:
            today_start = now.replace(hour=0, minute=0, second=0).isoformat()
            today_end = now.replace(hour=23, minute=59, second=59).isoformat()
            data["calendar_today"] = await cal_tool.run(
                {"start_date": today_start, "end_date": today_end},
                state={"user_id": owner_id},
            )
        except Exception as exc:
            logger.warning("Morning calendar failed: %s", exc)
            data["calendar_today"] = ""

    # --- Overnight important emails ---
    email_tool = registry.get("read_email")
    if email_tool:
        try:
            result = await email_tool.run(
                {"query": "is:unread is:important newer_than:12h", "limit": 3},
                state={"user_id": owner_id},
            )
            if "not connected" not in result.lower() and "no emails" not in result.lower():
                data["overnight_emails"] = result
        except Exception as exc:
            logger.warning("Morning email check failed: %s", exc)

    # --- Yesterday's focus session stats ---
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    focus_stats_key = f"jarvis:focus:daily_stats:{owner_id}:{yesterday}"
    try:
        focus_raw = await redis.cache_get(focus_stats_key)
        if focus_raw:
            data["yesterday_focus_stats"] = focus_raw
    except Exception:
        pass

    # --- Yesterday's heartbeat log (for activity summary) ---
    yesterday_log_key = f"jarvis:heartbeat:log:{yesterday}"
    try:
        log_raw = await redis.cache_get(yesterday_log_key)
        if log_raw:
            entries = json.loads(log_raw)
            noteworthy_count = sum(1 for e in entries if e.get("noteworthy"))
            data["yesterday_activity"] = (
                f"{len(entries)} heartbeat cycles, {noteworthy_count} noteworthy notifications"
            )
    except Exception:
        pass

    # --- Pending reminders for today ---
    from app.models.reminder import Reminder
    try:
        today_end_utc = now.replace(hour=23, minute=59, second=59).astimezone(timezone.utc)
        result = await db.execute(
            select(Reminder)
            .where(
                Reminder.user_id == owner_id,
                Reminder.is_delivered.is_(False),
                Reminder.remind_at <= today_end_utc,
            )
            .order_by(Reminder.remind_at.asc())
            .limit(5)
        )
        reminders = result.scalars().all()
        if reminders:
            lines = []
            for r in reminders:
                remind_mtn = r.remind_at.astimezone(_MTN) if r.remind_at.tzinfo else r.remind_at
                lines.append(f"- {r.message} at {remind_mtn.strftime('%I:%M %p')}")
            data["todays_reminders"] = "\n".join(lines)
    except Exception as exc:
        logger.warning("Morning reminder check failed: %s", exc)

    return data


def get_enhanced_morning_prompt() -> str:
    """Return the enhanced morning briefing prompt template.

    Exposed so the cron endpoint can use it.
    """
    return _ENHANCED_MORNING_PROMPT


# =============================================================================
# Focus session management helpers
# =============================================================================

async def start_focus_session(
    owner_id: str,
    duration_minutes: int = 60,
    label: str = "",
) -> dict[str, Any]:
    """Start a focus session for the owner. Suppresses non-emergency notifications.

    Call from a JARVIS tool when the user says "start a focus session" or
    "I need to concentrate for an hour".
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    now = datetime.now(tz=_MTN)
    suppress_until = now + timedelta(minutes=duration_minutes)

    session_data = {
        "started_at": now.isoformat(),
        "duration_minutes": duration_minutes,
        "suppress_until": suppress_until.isoformat(),
        "label": label,
    }

    key = f"focus_session:{owner_id}:active"
    await redis.cache_set(key, json.dumps(session_data), ttl=duration_minutes * 60 + 300)

    logger.info(
        "Focus session started for user %s: %d min, label=%s",
        owner_id, duration_minutes, label,
    )
    return {"status": "started", "session": session_data}


async def end_focus_session(owner_id: str) -> dict[str, Any]:
    """End an active focus session and return any queued notifications.

    Call from a JARVIS tool or automatically when the session expires.
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    key = f"focus_session:{owner_id}:active"

    session_raw = await redis.cache_get(key)
    if not session_raw:
        return {"status": "no_active_session", "queued_notifications": []}

    session = json.loads(session_raw)
    await redis.cache_delete(key)

    # Track daily focus stats
    now = datetime.now(tz=_MTN)
    started_at = datetime.fromisoformat(session["started_at"])
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=_MTN)
    actual_minutes = int((now - started_at).total_seconds() / 60)

    today = now.strftime("%Y-%m-%d")
    stats_key = f"jarvis:focus:daily_stats:{owner_id}:{today}"
    try:
        raw = await redis.cache_get(stats_key)
        stats = json.loads(raw) if raw else {"sessions": 0, "total_minutes": 0, "labels": []}
        stats["sessions"] += 1
        stats["total_minutes"] += actual_minutes
        if session.get("label"):
            stats["labels"].append(session["label"])
        await redis.cache_set(stats_key, json.dumps(stats), ttl=86400 * 2)
    except Exception as exc:
        logger.warning("Failed to update focus stats: %s", exc)

    # Drain queued notifications
    queued = await _drain_focus_queue(owner_id, redis)

    logger.info(
        "Focus session ended for user %s: %d actual minutes, %d queued notifications",
        owner_id, actual_minutes, len(queued),
    )

    return {
        "status": "ended",
        "actual_minutes": actual_minutes,
        "queued_notifications": queued,
    }


# =============================================================================
# Main heartbeat entry point (enhanced)
# =============================================================================

async def run_heartbeat(db: AsyncSession) -> dict[str, Any]:
    """Execute a single heartbeat cycle.

    Enhanced flow:
    1. Gather data from available sources
    2. Check focus session status
    3. Score each finding for urgency (Gemini-powered)
    4. Apply threshold filtering based on time-of-day + focus state
    5. Aggregate passing items into a batched digest
    6. Deliver via appropriate channel (or queue if focus session)
    7. Track engagement metrics
    8. Store results in Redis

    Returns a status dict with findings, scores, contact method, and delivery result.
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

    # 3. Get Redis and check focus session
    redis = await get_redis_client()
    focus_session = await _check_focus_session(owner_id, redis)
    results["focus_session_active"] = focus_session is not None
    if focus_session:
        logger.info(
            "Focus session active for user %s (label: %s, until: %s)",
            owner_id,
            focus_session.get("label", ""),
            focus_session.get("suppress_until", ""),
        )

    # 4. Check for queued notifications from a previous focus session
    #    (deliver them now if focus has ended)
    queued_items = []
    if not focus_session:
        queued_items = await _drain_focus_queue(owner_id, redis)
        if queued_items:
            logger.info("Found %d queued notifications from previous focus session", len(queued_items))
            results["drained_focus_queue"] = len(queued_items)

    # 5. Gather data from all sources
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

    # 6. Legacy noteworthy check (still used for basic filtering)
    noteworthy, reason = await _is_noteworthy(findings, redis)
    results["noteworthy"] = noteworthy
    results["reason"] = reason

    if not noteworthy and not queued_items:
        logger.info("Heartbeat: nothing noteworthy (%s) -- skipping contact", reason)
        await _store_heartbeat_result(redis, results)
        return results

    # 7. Score urgency for each finding (Gemini-powered contextual intelligence)
    scored_items = await score_notification_urgency(
        findings, method, redis, owner_id, focus_session,
    )
    results["urgency_scores"] = {
        item["category"]: item["urgency"] for item in scored_items
    }

    # 8. Determine threshold based on context
    if focus_session:
        threshold = _THRESHOLD_FOCUS_SESSION
    elif method == "dnd":
        threshold = _THRESHOLD_EMERGENCY
    elif method == "text":
        threshold = _THRESHOLD_WORK_HOURS
    elif method == "call":
        threshold = _THRESHOLD_OFF_HOURS
    else:
        threshold = _THRESHOLD_WORK_HOURS

    results["urgency_threshold"] = threshold

    # 9. Filter items that meet the threshold
    passing_items = [item for item in scored_items if item["urgency"] >= threshold]
    suppressed_items = [item for item in scored_items if item["urgency"] < threshold]

    results["passing_count"] = len(passing_items)
    results["suppressed_count"] = len(suppressed_items)

    logger.info(
        "Urgency filtering: %d items pass threshold %d, %d suppressed",
        len(passing_items), threshold, len(suppressed_items),
    )

    # 10. If in a focus session, queue non-emergency suppressed items
    if focus_session and suppressed_items:
        await _queue_suppressed_notification(owner_id, redis, suppressed_items)

    # 11. Include any queued items from a past focus session
    if queued_items:
        for qi in queued_items:
            passing_items.append({
                "category": qi["category"],
                "content": qi["content"],
                "urgency": qi["urgency"],
                "reason": f"queued from focus session at {qi.get('queued_at', 'unknown')}",
            })

    if not passing_items:
        logger.info("Heartbeat: no items meet urgency threshold %d -- skipping contact", threshold)
        results["delivery"] = {"method": "threshold_filtered", "logged": True}
        await _store_heartbeat_result(redis, results)
        return results

    # 12. Compose aggregated digest
    summary = await _compose_aggregated_digest(passing_items)
    results["summary"] = summary
    logger.info("Heartbeat digest: %s", summary[:200])

    # 13. Deliver based on contact method
    if method == "dnd" and not any(item["urgency"] >= _THRESHOLD_EMERGENCY for item in passing_items):
        logger.info("Heartbeat: DND mode -- logging findings but not contacting")
        results["delivery"] = {"method": "dnd", "logged": True}
    elif method == "dnd":
        # Emergency during DND -- escalate to text
        logger.info("Heartbeat: EMERGENCY during DND -- escalating to text")
        delivery = await _send_text(summary)
        results["delivery"] = delivery
        results["delivery"]["escalated_from_dnd"] = True
    elif method == "text":
        delivery = await _send_text(summary)
        results["delivery"] = delivery
    elif method == "call":
        delivery = await _make_call(summary)
        results["delivery"] = delivery
    else:
        logger.warning("Heartbeat: unknown contact method %s", method)
        results["delivery"] = {"method": method, "error": "unknown method"}

    # 14. Track engagement for each delivered notification
    for item in passing_items:
        await track_notification_sent(
            item["category"], item["urgency"], redis, owner_id,
        )

    # 15. Store results in Redis
    await _store_heartbeat_result(redis, results)

    logger.info(
        "Heartbeat complete: method=%s noteworthy=%s threshold=%d passing=%d",
        method, noteworthy, threshold, len(passing_items),
    )

    # ── Trigger learning cycle (every 30 min — alternate heartbeat runs) ──
    try:
        from app.db.redis import get_redis_client as _get_redis
        _redis = await _get_redis()
        hb_count_raw = await _redis.cache_get("jarvis:heartbeat:run_count")
        hb_count = int(hb_count_raw) if hb_count_raw else 0
        await _redis.cache_set("jarvis:heartbeat:run_count", str(hb_count + 1), ttl=86400 * 365)

        if hb_count % 2 == 0:  # Every other heartbeat = every 30 min
            # Check if learning cycle is already running
            lock = await _redis.cache_get("jarvis:learning:cycle_lock")
            if not lock:
                import asyncio
                from app.services.continuous_learning import run_learning_cycle
                # Run in background — don't block the heartbeat
                asyncio.create_task(run_learning_cycle())
                logger.info("Heartbeat: triggered learning cycle (run #%d)", hb_count)
                results["learning_triggered"] = True
            else:
                logger.info("Heartbeat: learning cycle already running, skipped")
                results["learning_triggered"] = False
    except Exception as exc:
        logger.debug("Heartbeat: learning cycle trigger failed: %s", exc)

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
            "urgency_scores": results.get("urgency_scores", {}),
            "passing_count": results.get("passing_count", 0),
            "suppressed_count": results.get("suppressed_count", 0),
            "focus_session_active": results.get("focus_session_active", False),
        })
        await redis_client.cache_set(log_key, json.dumps(entries), ttl=86400 * 2)
    except Exception as exc:
        logger.warning("Failed to store heartbeat result in Redis: %s", exc)
