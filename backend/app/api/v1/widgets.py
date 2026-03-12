"""Dashboard widget endpoints for the JARVIS frontend.

Lightweight data endpoints that power HUD widgets: weather, calendar,
Google connection status, system info, email, reminders, health, and
the intelligent layout ordering endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import zoneinfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User

logger = logging.getLogger("jarvis.widgets")

router = APIRouter(prefix="/widgets", tags=["Widgets"])

_MTN = zoneinfo.ZoneInfo("America/Denver")


# ── Layout response models ──────────────────────────────────────────────

class WidgetConfig(BaseModel):
    type: str
    urgency: float
    visible: bool
    data_hint: str | None = None


class LayoutResponse(BaseModel):
    widgets: list[WidgetConfig]


@router.get("/weather")
async def get_weather(
    current_user: User = Depends(get_current_active_user),
    lat: float | None = None,
    lon: float | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return structured weather data for the user's location.

    Accepts optional lat/lon query params from browser geolocation.
    If provided, also updates the user's stored location.
    """
    from app.integrations.weather import WeatherClient

    # If browser sent geolocation, use it and persist
    use_coords = lat is not None and lon is not None

    if use_coords:
        # Persist geolocation to user preferences for other services
        try:
            prefs = current_user.preferences or {}
            loc = prefs.get("current_location", {})
            loc["latitude"] = lat
            loc["longitude"] = lon
            loc["source"] = "browser_geolocation"
            prefs["current_location"] = loc
            current_user.preferences = prefs
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(current_user, "preferences")
            await db.commit()
        except Exception:
            logger.debug("Could not persist geolocation", exc_info=True)

    # Determine location from user preferences or default
    prefs = current_user.preferences or {}
    location = prefs.get("current_location", {})
    city = location.get("city", "Orem")
    country = location.get("country", "US")
    # OWM wants "City,CountryCode" format (NOT state names/abbreviations)
    location_str = f"{city},{country}" if country else city

    try:
        async with WeatherClient() as client:
            if use_coords:
                current = await client.get_current(lat=lat, lon=lon, units="imperial")
            else:
                current = await client.get_current(city=location_str, units="imperial")

            if "error" in current:
                return {"error": current["error"], "location": location_str}

            # Also get forecast
            if use_coords:
                forecast_data = await client.get_forecast(
                    lat=lat, lon=lon, units="imperial", days=3,
                )
            else:
                forecast_data = await client.get_forecast(
                    city=location_str, units="imperial", days=3,
                )
            forecast = forecast_data.get("forecast", []) if "error" not in forecast_data else []

            return {
                "location": current.get("location", location_str),
                "temperature": current.get("temperature"),
                "feels_like": current.get("feels_like"),
                "temp_min": current.get("temp_min"),
                "temp_max": current.get("temp_max"),
                "description": current.get("description", ""),
                "humidity": current.get("humidity"),
                "wind_speed": current.get("wind_speed"),
                "clouds": current.get("clouds"),
                "icon": current.get("icon", ""),
                "units": "F",
                "forecast": [
                    {
                        "date": day.get("date"),
                        "description": day.get("description"),
                        "temp_min": day.get("temp_min"),
                        "temp_max": day.get("temp_max"),
                    }
                    for day in forecast[:3]
                ],
            }
    except Exception as exc:
        logger.warning("Weather widget failed: %s", exc)
        return {"error": str(exc), "location": location_str}


@router.get("/calendar")
async def get_calendar(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return today's calendar events (requires Google OAuth)."""
    prefs = current_user.preferences or {}
    google_tokens = prefs.get("google_tokens")

    if not google_tokens:
        return {"connected": False, "events": [], "message": "Google not connected"}

    try:
        from app.integrations.calendar import CalendarClient

        now = datetime.now(tz=_MTN)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # OAuth stores access token as "token", CalendarClient expects "access_token"
        if "token" in google_tokens and "access_token" not in google_tokens:
            google_tokens["access_token"] = google_tokens["token"]
        client = CalendarClient(credentials=google_tokens)
        events = await client.list_events(
            time_min=today_start.isoformat(),
            time_max=today_end.isoformat(),
            max_results=5,
        )

        return {
            "connected": True,
            "events": [
                {
                    "title": e.get("title", "Untitled"),
                    "start": e.get("start", ""),
                    "end": e.get("end", ""),
                    "location": e.get("location", ""),
                }
                for e in events
            ],
        }
    except Exception as exc:
        logger.warning("Calendar widget failed: %s", exc)
        return {"connected": True, "events": [], "error": str(exc)}


@router.get("/system-health")
async def system_health_widget(
    current_user: User = Depends(get_current_active_user),
    force: bool = False,
) -> dict[str, Any]:
    """Return system health data for the dashboard widget.

    Results are cached for 5 minutes in Redis.  Pass ``?force=true`` to
    bypass the cache and trigger a fresh probe of all subsystems.
    """
    from app.services.system_monitor import get_system_health

    try:
        return await get_system_health(force_refresh=force)
    except Exception as exc:
        logger.warning("System health widget failed: %s", exc)
        return {"error": str(exc), "overall": "unknown"}


@router.get("/deploy-status")
async def deploy_status(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Get the latest Railway deployment status for the JARVIS backend service."""
    from app.services.system_monitor import get_railway_deploy_status

    try:
        return await get_railway_deploy_status()
    except Exception as exc:
        logger.warning("Deploy status widget failed: %s", exc)
        return {"error": str(exc)}


@router.get("/status")
async def get_system_status(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return system status and connection info for dashboard widgets."""
    prefs = current_user.preferences or {}
    google_connected = prefs.get("google_connected", False) and "google_tokens" in prefs

    # Check heartbeat status
    heartbeat_status = None
    try:
        from app.db.redis import get_redis_client
        import json

        r = await get_redis_client()
        last_raw = await r.cache_get("jarvis:heartbeat:last_result")
        if last_raw:
            heartbeat_status = json.loads(last_raw)
    except Exception:
        pass

    ntp_synced = False
    try:
        from app.utils.ntp_time import ntp_now
        now = ntp_now().astimezone(_MTN)
        ntp_synced = True
    except Exception:
        now = datetime.now(tz=_MTN)

    return {
        "google_connected": google_connected,
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d"),
        "timezone": "Mountain Time",
        "ntp_synced": ntp_synced,
        "ntp_server": "time.apple.com",
        "heartbeat": heartbeat_status,
        "services": {
            "weather_api": bool(settings.WEATHER_API_KEY),
            "elevenlabs": bool(settings.ELEVENLABS_API_KEY),
            "cerebras": bool(settings.CEREBRAS_API_KEY),
            "google_oauth": bool(settings.GOOGLE_CLIENT_ID),
        },
    }


# ── Email Widget ────────────────────────────────────────────────────────

_NOREPLY_PATTERNS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "notifications@", "notification@", "notify@", "mailer-daemon",
    "postmaster@", "bounce@", "auto-confirm", "automated@",
    "support@", "help@", "info@", "hello@", "team@", "billing@",
    "accounts@", "security@", "alerts@", "alert@", "updates@",
    "news@", "newsletter@", "marketing@", "promo@", "promotions@",
    "feedback@", "survey@", "receipts@", "orders@", "shipping@",
    "delivery@", "tracking@", "confirm@", "verification@",
    "service@", "services@", "admin@", "system@",
    "@github.com", "@linkedin.com", "@facebookmail.com",
    "@accounts.google.com", "@google.com", "@apple.com",
    "@amazon.com", "@paypal.com", "@stripe.com",
    "@notion.so", "@slack.com", "@discord.com",
    "@vercel.com", "@railway.app", "@netlify.com",
    "@circleci.com", "@travis-ci.com", "builds@",
)


def _is_noreply(from_addr: str) -> bool:
    """Check whether a From address looks like a no-reply / notification sender."""
    lower = from_addr.lower()
    return any(p in lower for p in _NOREPLY_PATTERNS)


async def _score_emails_with_gemini(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use Gemini to score each email's importance (1-10).

    Returns the email list with an added 'score' key. Falls back to the
    heuristic filter (exclude noreply senders) if Gemini is unavailable.
    """
    import httpx

    if not settings.GOOGLE_GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured")

    # Build a concise summary for the LLM
    email_summaries = []
    for i, e in enumerate(emails):
        email_summaries.append(
            f"{i + 1}. From: {e['from']}\n"
            f"   Subject: {e['subject']}\n"
            f"   Snippet: {e['snippet'][:150]}"
        )

    prompt = (
        "You are JARVIS, an AI assistant filtering emails for importance. "
        "Score each email 1-10. ONLY emails from REAL INDIVIDUAL PEOPLE deserve high scores.\n\n"
        "SCORE 8-10 (show to user):\n"
        "- A real person writing directly to the user (recruiter, colleague, friend, family)\n"
        "- Job interview invitations or offers from a named recruiter/hiring manager\n"
        "- Personal requests that need a human reply\n"
        "- Messages from professors, mentors, or managers addressed personally\n\n"
        "SCORE 1-4 (HIDE — do NOT score high):\n"
        "- ANY company/brand/service sending automated emails (Apple, Google, Amazon, GitHub, LinkedIn, etc.)\n"
        "- Receipts, order confirmations, shipping notifications\n"
        "- Security alerts, password resets, verification codes\n"
        "- Newsletters, marketing, promotional content\n"
        "- Build/deploy notifications, CI/CD alerts\n"
        "- Social media notifications (likes, follows, comments)\n"
        "- Billing statements, subscription renewals\n"
        "- Calendar auto-notifications\n"
        "- ANY email from a no-reply, notifications@, or automated address\n"
        "- ANY email where the sender is a company name, not a person's name\n\n"
        "KEY RULE: If the sender is a company/service/brand (not a person's first+last name), score 1-4.\n"
        "The user ONLY wants to see emails from actual humans who wrote to them personally.\n\n"
        "Reply ONLY with valid JSON: a list of objects with 'index' (1-based) "
        "and 'score' (integer 1-10). Example:\n"
        '[{"index": 1, "score": 9}, {"index": 2, "score": 2}]\n\n'
        "Emails:\n" + "\n".join(email_summaries)
    )

    model = "gemini-3.1-flash-lite-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            json=payload,
            params={"key": settings.GOOGLE_GEMINI_API_KEY},
        )
        resp.raise_for_status()
        data = resp.json()

    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    scores = json.loads(raw_text)

    # Build a lookup: 1-based index → score
    score_map: dict[int, int] = {}
    for entry in scores:
        idx = entry.get("index")
        score = entry.get("score", 1)
        if isinstance(idx, int) and isinstance(score, int):
            score_map[idx] = max(1, min(10, score))

    # Attach scores to emails
    scored: list[dict[str, Any]] = []
    for i, email in enumerate(emails):
        email_copy = dict(email)
        email_copy["score"] = score_map.get(i + 1, 5)
        scored.append(email_copy)

    return scored


def _is_automated_sender(from_addr: str) -> bool:
    """Check if sender is clearly a company/automated service, not a person."""
    lower = from_addr.lower()
    # Check noreply patterns first
    if _is_noreply(lower):
        return True
    # Known automated service senders
    _AUTOMATED_SENDERS = (
        "uber", "lyft", "doordash", "grubhub", "instacart",
        "mercury", "venmo", "cashapp", "zelle", "wise",
        "railway", "vercel", "netlify", "heroku", "render",
        "github", "gitlab", "bitbucket", "circleci", "travis",
        "stripe", "paypal", "square", "shopify",
        "amazon", "apple", "google", "microsoft",
        "linkedin", "facebook", "instagram", "twitter", "x.com",
        "slack", "discord", "notion", "figma", "canva",
        "dropbox", "icloud", "onedrive",
        "usps", "ups", "fedex", "dhl",
        "mint", "intuit", "turbotax", "irs.gov",
        "sprint", "t-mobile", "verizon", "at&t", "xfinity",
    )
    return any(s in lower for s in _AUTOMATED_SENDERS)


def _fallback_filter(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Heuristic fallback: return emails not from automated addresses."""
    return [e for e in emails if not _is_automated_sender(e.get("from", ""))]


@router.get("/email")
async def get_email_widget(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return important emails from the past week, filtered by LLM scoring.

    Results are cached in Redis for 15 minutes to avoid hammering Gmail.
    """
    prefs = current_user.preferences or {}
    google_tokens = prefs.get("google_tokens")

    if not google_tokens:
        return {"connected": False, "important": [], "total_checked": 0}

    # Normalise token key
    if "token" in google_tokens and "access_token" not in google_tokens:
        google_tokens["access_token"] = google_tokens["token"]

    # Check Redis cache first
    cache_key = f"jarvis:widget:email:{current_user.id}"
    try:
        from app.db.redis import get_redis_client

        redis = await get_redis_client()
        cached = await redis.cache_get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.debug("Redis cache miss or unavailable for email widget")
        redis = None

    try:
        from app.integrations.google_workspace import gmail_important_recent

        emails = await gmail_important_recent(google_tokens, max_results=15)
        total_checked = len(emails)

        if not emails:
            result = {"connected": True, "important": [], "total_checked": 0}
            await _cache_email_result(redis, cache_key, result)
            return result

        # Pre-filter: remove obvious automated/company senders before LLM
        emails = [e for e in emails if not _is_automated_sender(e.get("from", ""))]

        if not emails:
            result = {"connected": True, "important": [], "total_checked": total_checked}
            await _cache_email_result(redis, cache_key, result)
            return result

        # Try Gemini scoring; fall back to heuristic filter
        try:
            scored = await _score_emails_with_gemini(emails)
            important = [
                {
                    "subject": e["subject"],
                    "from": e["from"],
                    "date": e["date"],
                    "snippet": e["snippet"],
                }
                for e in scored
                if e.get("score", 0) >= 8
            ]
        except Exception as gemini_exc:
            logger.warning("Gemini email scoring failed, using fallback: %s", gemini_exc)
            filtered = _fallback_filter(emails)
            important = [
                {
                    "subject": e["subject"],
                    "from": e["from"],
                    "date": e["date"],
                    "snippet": e["snippet"],
                }
                for e in filtered
            ]

        result = {
            "connected": True,
            "important": important,
            "total_checked": total_checked,
        }
        await _cache_email_result(redis, cache_key, result)
        return result

    except Exception as exc:
        logger.warning("Email widget failed: %s", exc)
        return {"connected": True, "important": [], "total_checked": 0, "error": str(exc)}


async def _cache_email_result(redis, cache_key: str, result: dict) -> None:
    """Cache the email widget result in Redis for 15 minutes."""
    if redis is None:
        return
    try:
        await redis.cache_set(cache_key, json.dumps(result), ttl=900)
    except Exception:
        logger.debug("Failed to cache email widget result")


# ── Reminders Widget ───────────────────────────────────────────────────

@router.get("/reminders")
async def get_reminders_widget(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return upcoming and overdue reminders for the current user."""
    from app.models.reminder import Reminder

    now = datetime.now(tz=timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    try:
        # Overdue: remind_at in the past, not delivered
        overdue_result = await db.execute(
            select(Reminder)
            .where(
                Reminder.user_id == current_user.id,
                Reminder.remind_at < now,
                Reminder.is_delivered == False,  # noqa: E712
            )
            .order_by(Reminder.remind_at.asc())
            .limit(10)
        )
        overdue = overdue_result.scalars().all()

        # Upcoming today: remind_at between now and end of today
        upcoming_result = await db.execute(
            select(Reminder)
            .where(
                Reminder.user_id == current_user.id,
                Reminder.remind_at >= now,
                Reminder.remind_at <= today_end,
                Reminder.is_delivered == False,  # noqa: E712
            )
            .order_by(Reminder.remind_at.asc())
            .limit(10)
        )
        upcoming = upcoming_result.scalars().all()

        return {
            "overdue": [
                {
                    "id": str(r.id),
                    "message": r.message,
                    "remind_at": r.remind_at.isoformat(),
                }
                for r in overdue
            ],
            "upcoming": [
                {
                    "id": str(r.id),
                    "message": r.message,
                    "remind_at": r.remind_at.isoformat(),
                }
                for r in upcoming
            ],
            "overdue_count": len(overdue),
            "upcoming_count": len(upcoming),
        }
    except Exception as exc:
        logger.warning("Reminders widget failed: %s", exc)
        return {"overdue": [], "upcoming": [], "overdue_count": 0, "upcoming_count": 0, "error": str(exc)}


# ── Intelligent Layout Endpoint ─────────────────────────────────────────

async def _score_weather(user: User) -> WidgetConfig:
    """Score weather urgency based on conditions."""
    try:
        from app.integrations.weather import WeatherClient

        prefs = user.preferences or {}
        location = prefs.get("current_location", {})
        city = location.get("city", "Orem")
        country = location.get("country", "US")
        location_str = f"{city},{country}" if country else city

        async with WeatherClient() as client:
            current = await client.get_current(city=location_str, units="imperial")

        if "error" in current:
            return WidgetConfig(type="weather", urgency=3.0, visible=True, data_hint="error")

        temp = current.get("temperature", 70)
        desc = (current.get("description") or "").lower()
        urgency = 3.0  # baseline

        # Temperature extremes
        if temp is not None:
            if temp > 100 or temp < 10:
                urgency = max(urgency, 8.5)
            elif temp > 95 or temp < 20:
                urgency = max(urgency, 6.5)

        # Severe weather keywords
        severe_keywords = ["thunder", "lightning", "tornado", "hurricane", "blizzard", "hail"]
        precip_keywords = ["rain", "snow", "storm", "shower", "sleet", "drizzle"]

        if any(kw in desc for kw in severe_keywords):
            urgency = max(urgency, 9.0)
            return WidgetConfig(type="weather", urgency=urgency, visible=True, data_hint="severe_weather")
        if any(kw in desc for kw in precip_keywords):
            urgency = max(urgency, 6.0)
            return WidgetConfig(type="weather", urgency=urgency, visible=True, data_hint="precipitation")

        return WidgetConfig(type="weather", urgency=urgency, visible=True)
    except Exception:
        logger.debug("Weather scoring failed", exc_info=True)
        return WidgetConfig(type="weather", urgency=3.0, visible=True)


async def _score_calendar(user: User) -> WidgetConfig:
    """Score calendar urgency based on upcoming events."""
    prefs = user.preferences or {}
    google_tokens = prefs.get("google_tokens")

    if not google_tokens:
        return WidgetConfig(type="calendar", urgency=2.0, visible=True, data_hint="not_connected")

    try:
        from app.integrations.calendar import CalendarClient

        now = datetime.now(tz=_MTN)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        if "token" in google_tokens and "access_token" not in google_tokens:
            google_tokens["access_token"] = google_tokens["token"]
        client = CalendarClient(credentials=google_tokens)
        events = await client.list_events(
            time_min=today_start.isoformat(),
            time_max=today_end.isoformat(),
            max_results=10,
        )

        if not events:
            return WidgetConfig(type="calendar", urgency=2.0, visible=True, data_hint="no_events")

        # Check for events starting within the next hour
        one_hour_from_now = now + timedelta(hours=1)
        imminent = False
        for event in events:
            start_str = event.get("start", "")
            if not start_str or len(start_str) <= 10:
                continue
            try:
                event_start = datetime.fromisoformat(start_str)
                if now <= event_start <= one_hour_from_now:
                    imminent = True
                    break
            except (ValueError, TypeError):
                continue

        if imminent:
            return WidgetConfig(type="calendar", urgency=8.0, visible=True, data_hint="imminent_event")

        return WidgetConfig(type="calendar", urgency=5.0, visible=True, data_hint="events_today")
    except Exception:
        logger.debug("Calendar scoring failed", exc_info=True)
        return WidgetConfig(type="calendar", urgency=3.0, visible=True)


async def _score_health(user: User, db: AsyncSession) -> WidgetConfig:
    """Score health urgency based on recent data."""
    from app.models.health import HealthSample

    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    try:
        # Check for recent heart rate
        hr_result = await db.execute(
            select(HealthSample)
            .where(
                HealthSample.user_id == user.id,
                HealthSample.sample_type == "heart_rate",
                HealthSample.start_date >= today_start - timedelta(hours=6),
            )
            .order_by(HealthSample.start_date.desc())
            .limit(1)
        )
        hr_sample = hr_result.scalar_one_or_none()

        # Check for sleep data
        sleep_result = await db.execute(
            select(func.sum(HealthSample.value))
            .where(
                HealthSample.user_id == user.id,
                HealthSample.sample_type == "sleep",
                HealthSample.start_date >= yesterday_start,
                HealthSample.start_date < today_start + timedelta(hours=12),
            )
        )
        sleep_total = sleep_result.scalar()

        urgency = 3.0

        # Heart rate anomaly (resting HR > 100 or < 45)
        if hr_sample:
            hr_val = hr_sample.value
            if hr_val > 100 or hr_val < 45:
                urgency = max(urgency, 7.5)
                return WidgetConfig(type="health", urgency=urgency, visible=True, data_hint="hr_anomaly")

        # No sleep data recorded
        if sleep_total is None:
            urgency = max(urgency, 6.0)
            return WidgetConfig(type="health", urgency=urgency, visible=True, data_hint="no_sleep_data")

        # Very little sleep (< 5 hours)
        if sleep_total < 5.0:
            urgency = max(urgency, 5.5)
            return WidgetConfig(type="health", urgency=urgency, visible=True, data_hint="low_sleep")

        return WidgetConfig(type="health", urgency=urgency, visible=True)
    except Exception:
        logger.debug("Health scoring failed", exc_info=True)
        return WidgetConfig(type="health", urgency=2.5, visible=True)


async def _score_email(user: User) -> WidgetConfig:
    """Score email urgency based on unread count."""
    prefs = user.preferences or {}
    google_tokens = prefs.get("google_tokens")

    if not google_tokens:
        return WidgetConfig(type="email", urgency=0.0, visible=False, data_hint="not_connected")

    try:
        from app.integrations.google_workspace import gmail_unread_count

        if "token" in google_tokens and "access_token" not in google_tokens:
            google_tokens["access_token"] = google_tokens["token"]

        result = await gmail_unread_count(google_tokens)
        unread = result.get("unread_count", 0)

        if unread > 10:
            return WidgetConfig(type="email", urgency=7.0, visible=True, data_hint="high_unread")
        elif unread > 0:
            return WidgetConfig(type="email", urgency=4.5, visible=True, data_hint="has_unread")
        else:
            return WidgetConfig(type="email", urgency=1.5, visible=True)
    except Exception:
        logger.debug("Email scoring failed", exc_info=True)
        return WidgetConfig(type="email", urgency=1.5, visible=True)


async def _score_reminders(user: User, db: AsyncSession) -> WidgetConfig:
    """Score reminders urgency based on overdue and upcoming."""
    from app.models.reminder import Reminder

    now = datetime.now(tz=timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    try:
        # Count overdue
        overdue_result = await db.execute(
            select(func.count())
            .select_from(Reminder)
            .where(
                Reminder.user_id == user.id,
                Reminder.remind_at < now,
                Reminder.is_delivered == False,  # noqa: E712
            )
        )
        overdue_count = overdue_result.scalar() or 0

        # Count upcoming today
        upcoming_result = await db.execute(
            select(func.count())
            .select_from(Reminder)
            .where(
                Reminder.user_id == user.id,
                Reminder.remind_at >= now,
                Reminder.remind_at <= today_end,
                Reminder.is_delivered == False,  # noqa: E712
            )
        )
        upcoming_count = upcoming_result.scalar() or 0

        if overdue_count > 0:
            return WidgetConfig(type="reminders", urgency=8.0, visible=True, data_hint="overdue")
        elif upcoming_count > 0:
            return WidgetConfig(type="reminders", urgency=5.0, visible=True, data_hint="due_today")
        else:
            return WidgetConfig(type="reminders", urgency=1.0, visible=True)
    except Exception:
        logger.debug("Reminders scoring failed", exc_info=True)
        return WidgetConfig(type="reminders", urgency=1.0, visible=True)


async def _score_system_status() -> WidgetConfig:
    """Score system status urgency."""
    try:
        services = {
            "weather_api": bool(settings.WEATHER_API_KEY),
            "elevenlabs": bool(settings.ELEVENLABS_API_KEY),
            "cerebras": bool(settings.CEREBRAS_API_KEY),
            "google_oauth": bool(settings.GOOGLE_CLIENT_ID),
        }
        all_up = all(services.values())
        any_down = not all_up

        if any_down:
            down_count = sum(1 for v in services.values() if not v)
            return WidgetConfig(
                type="system",
                urgency=7.0 if down_count > 1 else 5.5,
                visible=True,
                data_hint="degraded",
            )
        return WidgetConfig(type="system", urgency=1.5, visible=True)
    except Exception:
        return WidgetConfig(type="system", urgency=1.5, visible=True)


@router.get("/layout", response_model=LayoutResponse)
async def get_widget_layout(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> LayoutResponse:
    """Return an urgency-sorted list of widget configs.

    Each widget is scored independently and in parallel. The response
    is ordered by descending urgency so the frontend can render the
    most important widgets first.
    """
    # Run all scoring functions concurrently
    results = await asyncio.gather(
        _score_weather(current_user),
        _score_calendar(current_user),
        _score_health(current_user, db),
        _score_email(current_user),
        _score_reminders(current_user, db),
        _score_system_status(),
        return_exceptions=True,
    )

    widgets: list[WidgetConfig] = []
    for r in results:
        if isinstance(r, WidgetConfig):
            widgets.append(r)
        elif isinstance(r, BaseException):
            logger.warning("Widget scoring raised: %s", r)

    # Sort by urgency descending
    widgets.sort(key=lambda w: w.urgency, reverse=True)

    return LayoutResponse(widgets=widgets)


@router.get("/habits")
async def get_habits_widget(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return today's habit summary for the dashboard widget."""
    from app.models.habit import Habit, HabitLog

    now = datetime.now(tz=_MTN)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    today_start_utc = today_start.astimezone(zoneinfo.ZoneInfo("UTC"))
    tomorrow_start_utc = tomorrow_start.astimezone(zoneinfo.ZoneInfo("UTC"))

    result = await db.execute(
        select(Habit)
        .where(Habit.user_id == current_user.id, Habit.is_active.is_(True))
        .order_by(Habit.sort_order.asc(), Habit.created_at.asc())
    )
    habits = result.scalars().all()

    if not habits:
        return {"total": 0, "completed": 0, "habits": []}

    habit_list = []
    completed_count = 0
    applicable_count = 0

    for habit in habits:
        today_date = now.date()
        applies_today = True
        if habit.frequency == "weekday" and today_date.weekday() >= 5:
            applies_today = False

        count_result = await db.execute(
            select(func.count())
            .select_from(HabitLog)
            .where(
                HabitLog.habit_id == habit.id,
                HabitLog.user_id == current_user.id,
                HabitLog.completed_at >= today_start_utc,
                HabitLog.completed_at < tomorrow_start_utc,
            )
        )
        today_count = count_result.scalar() or 0
        done = today_count >= habit.target_count

        if applies_today:
            applicable_count += 1
            if done:
                completed_count += 1

        habit_list.append({
            "id": str(habit.id),
            "name": habit.name,
            "icon": habit.icon,
            "color": habit.color,
            "target": habit.target_count,
            "today_count": today_count,
            "done": done,
            "frequency": habit.frequency,
            "applies_today": applies_today,
        })

    return {
        "total": applicable_count,
        "completed": completed_count,
        "habits": habit_list,
    }
