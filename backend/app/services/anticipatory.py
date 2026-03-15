"""
Anticipatory Intelligence for JARVIS.

Predicts needs and prepares information before Mr. Stark asks:
- Travel time alerts before meetings/appointments
- Assignment/deadline tracking and reminders
- Social awareness (missed calls, unanswered messages)
- Meeting preparation (pull relevant context before meetings)
- Weather-appropriate suggestions
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("jarvis.anticipatory")

_MTN = ZoneInfo("America/Denver")

# Alert priority levels
_PRIORITY_LOW = 3
_PRIORITY_MEDIUM = 5
_PRIORITY_HIGH = 7
_PRIORITY_URGENT = 9


async def run_anticipatory_check() -> dict[str, Any]:
    """Run all anticipatory checks and return a list of prioritised alerts.

    Checks:
    1. Upcoming calendar events and travel time
    2. Missed calls / unanswered messages
    3. Upcoming deadlines
    4. Prepares context for imminent meetings

    Returns a dict with alerts list sorted by priority (highest first),
    plus metadata about what was checked.
    """
    from app.config import settings
    from app.db.redis import get_redis_client

    logger.info("Running anticipatory intelligence check")
    redis = await get_redis_client()

    alerts: list[dict[str, Any]] = []
    checks_run: list[str] = []
    errors: list[str] = []

    # Determine owner ID for calendar lookups
    owner_id = await _get_owner_id()
    if not owner_id:
        logger.warning("No active owner found — skipping calendar checks")
    else:
        # Check upcoming travel
        try:
            travel_alerts = await _check_upcoming_travel(owner_id)
            alerts.extend(travel_alerts)
            checks_run.append("travel")
            logger.info("Travel check: %d alerts", len(travel_alerts))
        except Exception as exc:
            logger.exception("Travel check failed: %s", exc)
            errors.append(f"travel: {exc}")

    # Check missed communications
    try:
        comm_alerts = await _check_missed_communications()
        alerts.extend(comm_alerts)
        checks_run.append("communications")
        logger.info("Communications check: %d alerts", len(comm_alerts))
    except Exception as exc:
        logger.exception("Communications check failed: %s", exc)
        errors.append(f"communications: {exc}")

    # Check deadlines
    try:
        deadline_alerts = await _check_deadlines()
        alerts.extend(deadline_alerts)
        checks_run.append("deadlines")
        logger.info("Deadline check: %d alerts", len(deadline_alerts))
    except Exception as exc:
        logger.exception("Deadline check failed: %s", exc)
        errors.append(f"deadlines: {exc}")

    # Prepare context for upcoming meetings (only if we have upcoming events)
    meeting_alerts = [a for a in alerts if a.get("category") == "travel" and a.get("event")]
    for alert in meeting_alerts:
        event = alert.get("event", {})
        if event:
            try:
                context = await _prepare_meeting_context(event)
                if context:
                    alert["meeting_context"] = context
            except Exception as exc:
                logger.debug("Meeting context prep failed: %s", exc)

    # Sort by priority descending
    alerts.sort(key=lambda a: a.get("priority", 0), reverse=True)

    logger.info(
        "Anticipatory check complete: %d alerts, %d checks, %d errors",
        len(alerts), len(checks_run), len(errors),
    )

    return {
        "alerts": alerts,
        "alert_count": len(alerts),
        "checks_run": checks_run,
        "errors": errors,
        "timestamp": datetime.now(tz=_MTN).isoformat(),
    }


async def _check_upcoming_travel(owner_id: str) -> list[dict[str, Any]]:
    """Check calendar events for the next 4 hours and calculate travel alerts.

    For events with locations, attempts to calculate travel time via
    the Google Maps tool. Alerts if departure time is within 30 minutes.
    """
    from app.agents.tools import get_tool_registry

    alerts: list[dict[str, Any]] = []
    now = datetime.now(tz=_MTN)
    window_end = now + timedelta(hours=4)

    # Fetch calendar events via the tool registry
    registry = get_tool_registry()
    calendar_tool = registry.get("google_calendar")
    if not calendar_tool:
        logger.debug("Google Calendar tool not available — skipping travel check")
        return alerts

    try:
        events_result = await calendar_tool.run({
            "action": "list",
            "time_min": now.isoformat(),
            "time_max": window_end.isoformat(),
            "max_results": 10,
        })

        # Parse events from tool result
        events = _parse_calendar_events(events_result)
    except Exception as exc:
        logger.debug("Calendar fetch failed: %s", exc)
        return alerts

    for event in events:
        location = event.get("location", "")
        if not location:
            continue

        event_start_str = event.get("start", "")
        if not event_start_str:
            continue

        try:
            event_start = datetime.fromisoformat(event_start_str)
            if event_start.tzinfo is None:
                event_start = event_start.replace(tzinfo=_MTN)
        except (ValueError, TypeError):
            continue

        minutes_until = (event_start - now).total_seconds() / 60
        if minutes_until < 0 or minutes_until > 240:
            continue

        # Attempt travel time calculation via Google Maps tool
        travel_minutes = await _estimate_travel_time(registry, location)
        buffer_minutes = 15
        departure_in = minutes_until - travel_minutes - buffer_minutes

        event_summary = event.get("summary", "Event")

        if departure_in <= 30:
            if departure_in <= 0:
                message = (
                    f"You should already be en route to {event_summary} "
                    f"at {location}. Event starts in {int(minutes_until)} minutes."
                )
                priority = _PRIORITY_URGENT
            elif departure_in <= 15:
                message = (
                    f"{event_summary} in {int(minutes_until)} minutes at {location}. "
                    f"Traffic suggests leaving in the next {int(departure_in)} minutes."
                )
                priority = _PRIORITY_HIGH
            else:
                message = (
                    f"{event_summary} in {int(minutes_until)} minutes at {location}. "
                    f"Estimated travel time: {int(travel_minutes)} minutes. "
                    f"Leave in about {int(departure_in)} minutes."
                )
                priority = _PRIORITY_MEDIUM

            alerts.append({
                "message": message,
                "priority": priority,
                "category": "travel",
                "event": event,
                "travel_minutes": travel_minutes,
                "departure_in_minutes": max(0, int(departure_in)),
            })

    return alerts


async def _check_missed_communications() -> list[dict[str, Any]]:
    """Check for missed FaceTime calls and unread iMessages from important contacts.

    Uses the Mac Mini agent to run AppleScript queries against
    Messages and FaceTime on the Mac Mini.
    """
    from app.config import settings
    from app.integrations.mac_mini import remote_exec, is_configured

    alerts: list[dict[str, Any]] = []

    if not is_configured():
        logger.debug("Mac Mini not configured — skipping communications check")
        return alerts

    # Check for recent missed FaceTime calls via CallServices database
    try:
        result = await remote_exec(
            command=(
                'sqlite3 ~/Library/Application\\ Support/CallHistoryDB/CallHistory.storedata '
                '"SELECT ZADDRESS, ZDURATION, datetime(ZDATE + 978307200, \'unixepoch\', \'localtime\') '
                'FROM ZCALLRECORD WHERE ZANSWERED = 0 AND ZORIGINATED = 0 '
                'AND ZDATE > (strftime(\'%%s\', \'now\') - 978307200 - 86400) '
                'ORDER BY ZDATE DESC LIMIT 10"'
            ),
            timeout=15,
        )

        if result.get("success") and result.get("stdout", "").strip():
            lines = result["stdout"].strip().split("\n")
            for line in lines:
                parts = line.split("|")
                if len(parts) >= 3:
                    caller = parts[0].strip()
                    call_time = parts[2].strip()
                    display_name = _resolve_contact_name(caller)
                    alerts.append({
                        "message": f"Missed call from {display_name} at {call_time}.",
                        "priority": _PRIORITY_MEDIUM,
                        "category": "missed_call",
                        "contact": caller,
                        "time": call_time,
                    })
    except Exception as exc:
        logger.debug("Missed calls check failed: %s", exc)

    # Check for unread iMessages via AppleScript
    try:
        result = await remote_exec(
            command=(
                'sqlite3 ~/Library/Messages/chat.db '
                '"SELECT h.id, m.text, datetime(m.date/1000000000 + 978307200, \'unixepoch\', \'localtime\') '
                'FROM message m JOIN handle h ON m.handle_id = h.ROWID '
                'WHERE m.is_read = 0 AND m.is_from_me = 0 '
                'AND m.date > ((strftime(\'%%s\', \'now\') - 978307200) * 1000000000 - 86400000000000) '
                'ORDER BY m.date DESC LIMIT 10"'
            ),
            timeout=15,
        )

        if result.get("success") and result.get("stdout", "").strip():
            lines = result["stdout"].strip().split("\n")
            unread_by_contact: dict[str, int] = {}
            for line in lines:
                parts = line.split("|")
                if parts:
                    contact = parts[0].strip()
                    unread_by_contact[contact] = unread_by_contact.get(contact, 0) + 1

            for contact, count in unread_by_contact.items():
                display_name = _resolve_contact_name(contact)
                plural = "messages" if count > 1 else "message"
                alerts.append({
                    "message": f"{display_name} sent {count} unread {plural}. You might want to reply.",
                    "priority": _PRIORITY_MEDIUM,
                    "category": "unread_message",
                    "contact": contact,
                    "unread_count": count,
                })
    except Exception as exc:
        logger.debug("Unread messages check failed: %s", exc)

    # Elevate priority for family members
    for alert in alerts:
        contact = alert.get("contact", "")
        if _is_family_contact(contact):
            alert["priority"] = max(alert["priority"], _PRIORITY_HIGH)
            if "might want to" in alert.get("message", ""):
                alert["message"] = alert["message"].replace(
                    "You might want to reply.",
                    "Family — you should probably get back to them.",
                )

    return alerts


async def _check_deadlines() -> list[dict[str, Any]]:
    """Check for upcoming deadlines from calendar events and reminders.

    Looks for events with 'deadline', 'due', or 'assignment' in the
    title within the next 48 hours.
    """
    from app.agents.tools import get_tool_registry

    alerts: list[dict[str, Any]] = []
    now = datetime.now(tz=_MTN)
    window_end = now + timedelta(hours=48)

    registry = get_tool_registry()
    calendar_tool = registry.get("google_calendar")
    if not calendar_tool:
        return alerts

    try:
        events_result = await calendar_tool.run({
            "action": "list",
            "time_min": now.isoformat(),
            "time_max": window_end.isoformat(),
            "max_results": 20,
        })
        events = _parse_calendar_events(events_result)
    except Exception as exc:
        logger.debug("Calendar fetch for deadlines failed: %s", exc)
        return alerts

    deadline_keywords = {"deadline", "due", "assignment", "submit", "turn in", "final"}

    for event in events:
        summary = event.get("summary", "").lower()
        if not any(kw in summary for kw in deadline_keywords):
            continue

        event_start_str = event.get("start", "")
        if not event_start_str:
            continue

        try:
            event_start = datetime.fromisoformat(event_start_str)
            if event_start.tzinfo is None:
                event_start = event_start.replace(tzinfo=_MTN)
        except (ValueError, TypeError):
            continue

        hours_until = (event_start - now).total_seconds() / 3600

        if hours_until <= 0:
            continue
        elif hours_until <= 6:
            priority = _PRIORITY_URGENT
            urgency = "due in less than 6 hours"
        elif hours_until <= 24:
            priority = _PRIORITY_HIGH
            urgency = f"due in {int(hours_until)} hours"
        else:
            priority = _PRIORITY_MEDIUM
            urgency = f"due in {int(hours_until)} hours"

        alerts.append({
            "message": f"{event.get('summary', 'Deadline')} — {urgency}.",
            "priority": priority,
            "category": "deadline",
            "event": event,
            "hours_until": round(hours_until, 1),
        })

    return alerts


async def _prepare_meeting_context(event: dict[str, Any]) -> str:
    """Prepare context for an upcoming meeting.

    Searches the knowledge base and contacts for information about
    the attendees and topic, then synthesises a brief context note.
    """
    from app.agents.tools import get_tool_registry
    from app.integrations.llm.factory import get_llm_client

    summary = event.get("summary", "")
    attendees = event.get("attendees", [])
    description = event.get("description", "")
    location = event.get("location", "")

    # Gather search terms from the event
    search_terms: list[str] = []
    if summary:
        search_terms.append(summary)
    for attendee in attendees[:5]:
        name = attendee.get("displayName") or attendee.get("email", "")
        if name:
            search_terms.append(name)

    if not search_terms:
        return ""

    # Search knowledge base for relevant context
    context_parts: list[str] = []

    try:
        from app.db.qdrant import get_qdrant_store
        from app.graphrag.vector_store import VectorStore

        qdrant = get_qdrant_store()
        vector_store = VectorStore(qdrant_store=qdrant)

        for term in search_terms[:3]:
            try:
                hits = await vector_store.search_similar(
                    query=term, limit=2, min_score=0.7,
                )
                for hit in hits:
                    text = hit.get("text", "")[:300]
                    if text:
                        context_parts.append(f"[Knowledge] {text}")
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Knowledge base search for meeting context failed: %s", exc)

    # Search contacts via tool registry
    registry = get_tool_registry()
    contacts_tool = registry.get("contacts_search")
    if contacts_tool:
        for attendee in attendees[:3]:
            name = attendee.get("displayName") or attendee.get("email", "")
            if name:
                try:
                    result = await contacts_tool.run({"query": name})
                    if result and len(result) > 20:
                        context_parts.append(f"[Contact] {result[:300]}")
                except Exception:
                    pass

    if not context_parts:
        return ""

    # Synthesise via LLM
    combined_context = "\n\n".join(context_parts[:10])

    try:
        llm = get_llm_client("gemini")
        response = await llm.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are JARVIS, preparing Mr. Stark for a meeting.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Meeting: {summary}\n"
                        f"Location: {location}\n"
                        f"Attendees: {', '.join(a.get('displayName', a.get('email', '')) for a in attendees[:5])}\n"
                        f"Description: {description[:500]}\n\n"
                        f"Relevant context:\n{combined_context}\n\n"
                        "Write a 2-3 sentence briefing note covering who these people are "
                        "and anything relevant Mr. Stark should know going in."
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=300,
        )
        return response["content"].strip()
    except Exception as exc:
        logger.debug("Meeting context synthesis failed: %s", exc)
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════


async def _get_owner_id() -> Optional[str]:
    """Retrieve the active owner's user ID from the database."""
    try:
        from app.db.session import async_session_factory
        from app.models.user import User
        from sqlalchemy import select

        async with async_session_factory() as db:
            result = await db.execute(
                select(User.id).where(User.is_active.is_(True)).limit(1)
            )
            row = result.scalar_one_or_none()
            return str(row) if row else None
    except Exception as exc:
        logger.debug("Could not fetch owner ID: %s", exc)
        return None


async def _estimate_travel_time(
    registry: dict[str, Any],
    destination: str,
) -> float:
    """Estimate travel time in minutes to a destination.

    Attempts to use the Google Maps tool from the tool registry.
    Falls back to a conservative default of 30 minutes.
    """
    default_minutes = 30.0

    maps_tool = registry.get("google_maps") or registry.get("maps")
    if not maps_tool:
        return default_minutes

    try:
        result = await maps_tool.run({
            "action": "directions",
            "destination": destination,
        })
        if isinstance(result, str):
            # Try to parse travel time from the result text
            import re
            time_match = re.search(r'(\d+)\s*min', result)
            if time_match:
                return float(time_match.group(1))
        elif isinstance(result, dict):
            duration = result.get("duration_minutes") or result.get("duration", {}).get("value", 0) / 60
            if duration > 0:
                return float(duration)
    except Exception as exc:
        logger.debug("Travel time estimation failed: %s", exc)

    return default_minutes


def _parse_calendar_events(events_result: Any) -> list[dict[str, Any]]:
    """Parse calendar events from tool output into a list of dicts.

    The calendar tool may return a JSON string, a dict, or a list.
    This normalises the output.
    """
    if not events_result:
        return []

    if isinstance(events_result, list):
        return events_result

    if isinstance(events_result, dict):
        return events_result.get("events", events_result.get("items", []))

    if isinstance(events_result, str):
        try:
            parsed = json.loads(events_result)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return parsed.get("events", parsed.get("items", []))
        except (json.JSONDecodeError, TypeError):
            pass

    return []


def _resolve_contact_name(identifier: str) -> str:
    """Attempt to resolve a phone number or email to a display name.

    For now returns the identifier cleaned up. Could be extended
    to look up the contacts database.
    """
    # Strip common prefixes for readability
    cleaned = identifier.strip()
    if cleaned.startswith("+1") and len(cleaned) == 12:
        # Format US phone number
        return f"({cleaned[2:5]}) {cleaned[5:8]}-{cleaned[8:]}"
    return cleaned


def _is_family_contact(identifier: str) -> bool:
    """Check if a contact identifier belongs to a known family member.

    Uses settings for known important numbers. Extend as needed.
    """
    try:
        from app.config import settings
        owner_phone = getattr(settings, "OWNER_PHONE", "")
        # Family numbers can be extended here
        family_indicators = {owner_phone} if owner_phone else set()
        return identifier.strip() in family_indicators
    except Exception:
        return False
