"""
Focus Session API — start, end, and track deep work / learning sessions.

Provides endpoints for JARVIS to manage focused work sessions with
duration tracking, distraction counting, and productivity ratings.
Stats aggregations cover weekly/monthly trends.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_or_service, get_db
from app.models.focus_session import FocusSession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Focus"])


# ── Schemas ──────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    title: str = Field(..., description="Session title, e.g. 'Physics - Quantum Mechanics'")
    category: Optional[str] = Field(None, description="Category: learning, deep_work, creative, admin")
    planned_duration_min: Optional[int] = Field(None, description="Target duration in minutes")


class EndSessionRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Session notes or reflections")
    energy_level: Optional[int] = Field(None, ge=1, le=5, description="Energy level 1-5")
    productivity_rating: Optional[int] = Field(None, ge=1, le=5, description="Productivity rating 1-5")
    distractions: Optional[int] = Field(None, ge=0, description="Override distraction count")


class FocusSessionOut(BaseModel):
    id: str
    title: str
    category: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    planned_duration_min: Optional[int] = None
    actual_duration_min: Optional[int] = None
    notes: Optional[str] = None
    distractions: int
    energy_level: Optional[int] = None
    productivity_rating: Optional[int] = None
    in_progress: bool


class FocusStatsResponse(BaseModel):
    period: str
    total_sessions: int
    total_focus_hours: float
    avg_session_min: float
    avg_productivity: Optional[float] = None
    avg_energy: Optional[float] = None
    total_distractions: int
    by_category: dict[str, dict]


# ── Helpers ──────────────────────────────────────────────────────────────

def _session_to_out(s: FocusSession) -> FocusSessionOut:
    return FocusSessionOut(
        id=str(s.id),
        title=s.title,
        category=s.category,
        started_at=s.started_at.isoformat(),
        ended_at=s.ended_at.isoformat() if s.ended_at else None,
        planned_duration_min=s.planned_duration_min,
        actual_duration_min=s.actual_duration_min,
        notes=s.notes,
        distractions=s.distractions,
        energy_level=s.energy_level,
        productivity_rating=s.productivity_rating,
        in_progress=s.ended_at is None,
    )


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/start", response_model=FocusSessionOut, status_code=status.HTTP_201_CREATED)
async def start_focus_session(
    body: StartSessionRequest,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Start a new focus session.

    If a session is already in progress it is returned unchanged — only one
    active session is allowed at a time.
    """
    # Check for existing in-progress session
    existing_result = await db.execute(
        select(FocusSession)
        .where(
            FocusSession.user_id == current_user.id,
            FocusSession.ended_at.is_(None),
        )
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        logger.info(
            "focus/start: user=%s already has session %s in progress",
            current_user.id, existing.id,
        )
        return _session_to_out(existing)

    session = FocusSession(
        user_id=current_user.id,
        title=body.title,
        category=body.category,
        started_at=datetime.now(timezone.utc),
        planned_duration_min=body.planned_duration_min,
        distractions=0,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "focus/start: user=%s session=%s title=%r category=%s planned=%s",
        current_user.id, session.id, session.title,
        session.category, session.planned_duration_min,
    )
    return _session_to_out(session)


@router.post("/end", response_model=FocusSessionOut)
async def end_focus_session(
    body: EndSessionRequest,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """End the current in-progress focus session.

    Computes actual_duration_min from started_at to now and stores
    optional notes, ratings, and a distraction count override.
    """
    result = await db.execute(
        select(FocusSession)
        .where(
            FocusSession.user_id == current_user.id,
            FocusSession.ended_at.is_(None),
        )
        .order_by(FocusSession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active focus session found.",
        )

    now = datetime.now(timezone.utc)
    duration_min = int((now - session.started_at).total_seconds() / 60)

    session.ended_at = now
    session.actual_duration_min = duration_min
    if body.notes is not None:
        session.notes = body.notes
    if body.energy_level is not None:
        session.energy_level = body.energy_level
    if body.productivity_rating is not None:
        session.productivity_rating = body.productivity_rating
    if body.distractions is not None:
        session.distractions = body.distractions

    await db.commit()
    await db.refresh(session)

    logger.info(
        "focus/end: user=%s session=%s duration=%dmin productivity=%s",
        current_user.id, session.id, duration_min, session.productivity_rating,
    )
    return _session_to_out(session)


@router.get("/current", response_model=Optional[FocusSessionOut])
async def get_current_session(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Return the currently active focus session, or null if none."""
    result = await db.execute(
        select(FocusSession)
        .where(
            FocusSession.user_id == current_user.id,
            FocusSession.ended_at.is_(None),
        )
        .order_by(FocusSession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if not session:
        return None
    return _session_to_out(session)


@router.get("/history", response_model=list[FocusSessionOut])
async def focus_history(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """List past (completed) focus sessions, newest first.

    Optional ``category`` filter and pagination via ``limit``/``offset``.
    """
    conditions = [
        FocusSession.user_id == current_user.id,
        FocusSession.ended_at.isnot(None),
    ]
    if category:
        conditions.append(FocusSession.category == category)

    result = await db.execute(
        select(FocusSession)
        .where(and_(*conditions))
        .order_by(FocusSession.started_at.desc())
        .offset(offset)
        .limit(limit)
    )
    sessions = result.scalars().all()
    return [_session_to_out(s) for s in sessions]


@router.get("/stats", response_model=FocusStatsResponse)
async def focus_stats(
    period: str = Query("week", description="Stats period: 'week' or 'month'"),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate focus stats for the past week or month.

    Returns total focus hours, average session length, productivity
    and energy averages, total distractions, and a per-category breakdown.
    """
    now = datetime.now(timezone.utc)
    if period == "month":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(days=7)

    result = await db.execute(
        select(FocusSession)
        .where(
            FocusSession.user_id == current_user.id,
            FocusSession.ended_at.isnot(None),
            FocusSession.started_at >= since,
        )
        .order_by(FocusSession.started_at.desc())
    )
    sessions = result.scalars().all()

    total_sessions = len(sessions)
    total_min = sum(s.actual_duration_min or 0 for s in sessions)
    total_hours = round(total_min / 60, 1)
    avg_min = round(total_min / total_sessions, 1) if total_sessions else 0.0

    rated = [s for s in sessions if s.productivity_rating is not None]
    avg_productivity: Optional[float] = (
        round(sum(s.productivity_rating for s in rated) / len(rated), 2)  # type: ignore[arg-type]
        if rated else None
    )
    energized = [s for s in sessions if s.energy_level is not None]
    avg_energy: Optional[float] = (
        round(sum(s.energy_level for s in energized) / len(energized), 2)  # type: ignore[arg-type]
        if energized else None
    )
    total_distractions = sum(s.distractions for s in sessions)

    # Per-category breakdown
    by_category: dict[str, dict] = {}
    for s in sessions:
        cat = s.category or "uncategorized"
        if cat not in by_category:
            by_category[cat] = {"sessions": 0, "total_min": 0, "total_hours": 0.0}
        by_category[cat]["sessions"] += 1
        by_category[cat]["total_min"] += s.actual_duration_min or 0
        by_category[cat]["total_hours"] = round(by_category[cat]["total_min"] / 60, 1)

    return FocusStatsResponse(
        period=period,
        total_sessions=total_sessions,
        total_focus_hours=total_hours,
        avg_session_min=avg_min,
        avg_productivity=avg_productivity,
        avg_energy=avg_energy,
        total_distractions=total_distractions,
        by_category=by_category,
    )


@router.post("/distraction", response_model=FocusSessionOut)
async def log_distraction(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Increment the distraction counter on the active focus session."""
    result = await db.execute(
        select(FocusSession)
        .where(
            FocusSession.user_id == current_user.id,
            FocusSession.ended_at.is_(None),
        )
        .order_by(FocusSession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active focus session found.",
        )

    session.distractions = (session.distractions or 0) + 1
    await db.commit()
    await db.refresh(session)

    logger.info(
        "focus/distraction: user=%s session=%s distractions=%d",
        current_user.id, session.id, session.distractions,
    )
    return _session_to_out(session)
