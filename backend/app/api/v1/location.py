"""Location history API — timeline and travel data for map display."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_or_service, get_db
from app.core.encryption import decrypt_message
from app.models.location_history import LocationHistory
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Location"])


# -- Response schemas --------------------------------------------------------

from pydantic import BaseModel


class LocationPoint(BaseModel):
    id: str
    latitude: float
    longitude: float
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    created_at: str


class LocationDaySummary(BaseModel):
    date: str
    points: list[LocationPoint]
    cities: list[str]
    start_location: Optional[str] = None
    end_location: Optional[str] = None


class LocationTimelineResponse(BaseModel):
    days: list[LocationDaySummary]
    total_points: int


# -- Helpers -----------------------------------------------------------------

def _decrypt_coord(encrypted: Optional[str], fallback: float, user_id) -> float:
    """Return decrypted coordinate if available, else the plain float column."""
    if encrypted:
        try:
            return float(decrypt_message(encrypted, user_id))
        except (ValueError, TypeError):
            pass
    return fallback


def _format_location(city: Optional[str], state: Optional[str]) -> Optional[str]:
    parts = [p for p in [city, state] if p]
    return ", ".join(parts) if parts else None


# -- Endpoints ---------------------------------------------------------------

@router.get("/history", response_model=LocationTimelineResponse)
async def get_location_history(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Get location history grouped by day for timeline display."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(LocationHistory)
        .where(
            LocationHistory.user_id == current_user.id,
            LocationHistory.created_at >= cutoff,
        )
        .order_by(LocationHistory.created_at.desc())
    )
    entries = result.scalars().all()

    # Group by date
    day_groups: dict[str, list[LocationHistory]] = {}
    for entry in entries:
        day_key = entry.created_at.strftime("%Y-%m-%d")
        day_groups.setdefault(day_key, []).append(entry)

    days_list = []
    for day_key in sorted(day_groups.keys(), reverse=True):
        points = day_groups[day_key]
        # Sort chronologically within day
        points.sort(key=lambda p: p.created_at)

        cities = list(dict.fromkeys(
            p.city for p in points if p.city
        ))

        days_list.append(LocationDaySummary(
            date=day_key,
            points=[
                LocationPoint(
                    id=str(p.id),
                    latitude=_decrypt_coord(p.encrypted_lat, p.latitude, p.user_id),
                    longitude=_decrypt_coord(p.encrypted_lng, p.longitude, p.user_id),
                    city=p.city,
                    state=p.state,
                    country=p.country,
                    created_at=p.created_at.isoformat(),
                )
                for p in points
            ],
            cities=cities,
            start_location=_format_location(points[0].city, points[0].state),
            end_location=_format_location(points[-1].city, points[-1].state),
        ))

    return LocationTimelineResponse(
        days=days_list,
        total_points=len(entries),
    )


@router.get("/latest")
async def get_latest_location(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the most recent location entry."""
    result = await db.execute(
        select(LocationHistory)
        .where(LocationHistory.user_id == current_user.id)
        .order_by(LocationHistory.created_at.desc())
        .limit(1)
    )
    entry = result.scalar_one_or_none()

    if not entry:
        # Fall back to preferences
        prefs = current_user.preferences or {}
        loc = prefs.get("current_location")
        if loc:
            return {"source": "preferences", **loc}
        return {"source": "none"}

    return {
        "source": "history",
        "latitude": _decrypt_coord(entry.encrypted_lat, entry.latitude, entry.user_id),
        "longitude": _decrypt_coord(entry.encrypted_lng, entry.longitude, entry.user_id),
        "city": entry.city,
        "state": entry.state,
        "country": entry.country,
        "updated_at": entry.created_at.isoformat(),
    }


@router.get("/stats")
async def get_location_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get location statistics — unique cities, total points, etc."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(LocationHistory)
        .where(
            LocationHistory.user_id == current_user.id,
            LocationHistory.created_at >= cutoff,
        )
    )
    entries = result.scalars().all()

    cities = list(dict.fromkeys(e.city for e in entries if e.city))
    states = list(dict.fromkeys(e.state for e in entries if e.state))

    # Count unique days
    unique_days = len(set(e.created_at.strftime("%Y-%m-%d") for e in entries))

    return {
        "total_points": len(entries),
        "unique_days": unique_days,
        "unique_cities": cities,
        "unique_states": states,
        "period_days": days,
    }
