"""Dashboard widget endpoints for the JARVIS frontend.

Lightweight data endpoints that power HUD widgets: weather, calendar,
Google connection status, and system info.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import zoneinfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User

logger = logging.getLogger("jarvis.widgets")

router = APIRouter(prefix="/widgets", tags=["Widgets"])

_MTN = zoneinfo.ZoneInfo("America/Denver")


@router.get("/weather")
async def get_weather(
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Return structured weather data for the user's location."""
    from app.integrations.weather import WeatherClient

    # Determine location from user preferences or default
    prefs = current_user.preferences or {}
    location = prefs.get("current_location", {})
    city = location.get("city", "Orem")
    state = location.get("state", "Utah")
    location_str = f"{city}, {state}" if state else city

    try:
        async with WeatherClient() as client:
            current = await client.get_current(city=location_str, units="imperial")
            if "error" in current:
                return {"error": current["error"], "location": location_str}

            # Also get forecast
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

    now = datetime.now(tz=_MTN)

    return {
        "google_connected": google_connected,
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d"),
        "timezone": "Mountain Time",
        "heartbeat": heartbeat_status,
        "services": {
            "weather_api": bool(settings.WEATHER_API_KEY),
            "elevenlabs": bool(settings.ELEVENLABS_API_KEY),
            "cerebras": bool(settings.CEREBRAS_API_KEY),
            "google_oauth": bool(settings.GOOGLE_CLIENT_ID),
        },
    }
