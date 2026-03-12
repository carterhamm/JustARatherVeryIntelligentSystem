"""
Habits API -- create, track, and analyse habits with streak calculation.

Supports daily, weekday, weekly, and custom frequency habits with
completion logging, streak tracking, and summary statistics.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_or_service, get_db
from app.models.habit import Habit, HabitLog
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Habits"])


# -- Schemas ----------------------------------------------------------------

class HabitCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    frequency: str = Field("daily", pattern=r"^(daily|weekday|weekly|custom)$")
    target_count: int = Field(1, ge=1)
    icon: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, max_length=7)
    sort_order: int = 0


class HabitUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    frequency: Optional[str] = Field(None, pattern=r"^(daily|weekday|weekly|custom)$")
    target_count: Optional[int] = Field(None, ge=1)
    icon: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, max_length=7)
    sort_order: Optional[int] = None


class HabitLogCreate(BaseModel):
    notes: Optional[str] = Field(None, max_length=512)
    value: float = 1.0
    completed_at: Optional[datetime] = None  # defaults to now


class HabitResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    frequency: str
    target_count: int
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: str
    # Computed fields (populated in list endpoint)
    today_count: int = 0
    current_streak: int = 0


class HabitLogResponse(BaseModel):
    id: str
    habit_id: str
    completed_at: str
    notes: Optional[str] = None
    value: float


class HabitStatsResponse(BaseModel):
    habit_id: str
    habit_name: str
    current_streak: int
    longest_streak: int
    completion_rate: float  # 0.0-1.0, last 30 days
    total_completions: int
    last_30_days: list[dict[str, Any]]  # [{date, count}]


class HabitSummaryResponse(BaseModel):
    total_habits: int
    completed_today: int
    total_today: int
    completion_percentage: float
    habits: list[HabitResponse]


# -- Helpers ----------------------------------------------------------------

def _habit_to_dict(habit: Habit) -> dict[str, Any]:
    return {
        "id": str(habit.id),
        "name": habit.name,
        "description": habit.description,
        "frequency": habit.frequency,
        "target_count": habit.target_count,
        "icon": habit.icon,
        "color": habit.color,
        "is_active": habit.is_active,
        "sort_order": habit.sort_order,
        "created_at": habit.created_at.isoformat(),
    }


def _today_range() -> tuple[datetime, datetime]:
    """Return (start_of_today_utc, start_of_tomorrow_utc)."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return today_start, tomorrow_start


async def _get_today_count(
    db: AsyncSession, habit_id: uuid.UUID, user_id: uuid.UUID,
) -> int:
    """Count completions for a habit today."""
    today_start, tomorrow_start = _today_range()
    result = await db.execute(
        select(func.count())
        .select_from(HabitLog)
        .where(
            HabitLog.habit_id == habit_id,
            HabitLog.user_id == user_id,
            HabitLog.completed_at >= today_start,
            HabitLog.completed_at < tomorrow_start,
        )
    )
    return result.scalar() or 0


async def _calculate_streak(
    db: AsyncSession,
    habit: Habit,
    user_id: uuid.UUID,
) -> int:
    """Calculate current streak: consecutive days with >= target_count completions.

    Goes backwards from today, breaking on any missed applicable day.
    """
    target = habit.target_count
    today = datetime.now(timezone.utc).date()
    streak = 0

    for days_back in range(0, 365):  # max 1 year lookback
        check_date = today - timedelta(days=days_back)

        # Skip non-applicable days based on frequency
        if habit.frequency == "weekday" and check_date.weekday() >= 5:
            continue  # skip weekends
        if habit.frequency == "weekly":
            # Only check once per week (on the same weekday as today)
            if check_date.weekday() != today.weekday() and days_back > 0:
                continue

        day_start = datetime(
            check_date.year, check_date.month, check_date.day,
            tzinfo=timezone.utc,
        )
        day_end = day_start + timedelta(days=1)

        result = await db.execute(
            select(func.count())
            .select_from(HabitLog)
            .where(
                HabitLog.habit_id == habit.id,
                HabitLog.user_id == user_id,
                HabitLog.completed_at >= day_start,
                HabitLog.completed_at < day_end,
            )
        )
        count = result.scalar() or 0

        if count >= target:
            streak += 1
        else:
            # Allow today to be incomplete without breaking the streak
            if days_back == 0:
                continue
            break

    return streak


async def _calculate_longest_streak(
    db: AsyncSession,
    habit: Habit,
    user_id: uuid.UUID,
) -> int:
    """Calculate the longest streak ever for a habit."""
    # Get all logs ordered by date
    result = await db.execute(
        select(HabitLog.completed_at)
        .where(
            HabitLog.habit_id == habit.id,
            HabitLog.user_id == user_id,
        )
        .order_by(HabitLog.completed_at.asc())
    )
    logs = result.scalars().all()
    if not logs:
        return 0

    # Group by date
    dates_with_counts: dict[date, int] = {}
    for completed_at in logs:
        d = completed_at.date()
        dates_with_counts[d] = dates_with_counts.get(d, 0) + 1

    # Find longest consecutive run of qualifying dates
    target = habit.target_count
    qualifying_dates = sorted(d for d, c in dates_with_counts.items() if c >= target)
    if not qualifying_dates:
        return 0

    longest = 1
    current = 1
    for i in range(1, len(qualifying_dates)):
        expected_gap = 1
        if habit.frequency == "weekday":
            # Account for weekends
            prev = qualifying_dates[i - 1]
            curr = qualifying_dates[i]
            gap = (curr - prev).days
            # Skip weekends: Fri->Mon = 3 days gap is OK
            if prev.weekday() == 4 and gap <= 3:
                current += 1
                longest = max(longest, current)
                continue
            elif gap == 1:
                current += 1
                longest = max(longest, current)
                continue
            else:
                current = 1
                continue
        elif habit.frequency == "weekly":
            expected_gap = 7

        if (qualifying_dates[i] - qualifying_dates[i - 1]).days == expected_gap:
            current += 1
        else:
            current = 1
        longest = max(longest, current)

    return longest


# -- Endpoints --------------------------------------------------------------

@router.post("", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
async def create_habit(
    body: HabitCreate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Create a new habit."""
    habit = Habit(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        frequency=body.frequency,
        target_count=body.target_count,
        icon=body.icon,
        color=body.color,
        sort_order=body.sort_order,
    )
    db.add(habit)
    await db.commit()
    await db.refresh(habit)

    logger.info("Habit created: user=%s name=%s", current_user.id, habit.name)
    return HabitResponse(**_habit_to_dict(habit))


@router.get("", response_model=list[HabitResponse])
async def list_habits(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """List user's active habits with today's completion count and current streak."""
    result = await db.execute(
        select(Habit)
        .where(Habit.user_id == current_user.id, Habit.is_active.is_(True))
        .order_by(Habit.sort_order.asc(), Habit.created_at.asc())
    )
    habits = result.scalars().all()

    out = []
    for habit in habits:
        d = _habit_to_dict(habit)
        d["today_count"] = await _get_today_count(db, habit.id, current_user.id)
        d["current_streak"] = await _calculate_streak(db, habit, current_user.id)
        out.append(HabitResponse(**d))
    return out


@router.put("/{habit_id}", response_model=HabitResponse)
async def update_habit(
    habit_id: uuid.UUID,
    body: HabitUpdate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Update a habit's properties."""
    result = await db.execute(
        select(Habit).where(Habit.id == habit_id, Habit.user_id == current_user.id)
    )
    habit = result.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(habit, field, value)

    await db.commit()
    await db.refresh(habit)

    d = _habit_to_dict(habit)
    d["today_count"] = await _get_today_count(db, habit.id, current_user.id)
    d["current_streak"] = await _calculate_streak(db, habit, current_user.id)
    return HabitResponse(**d)


@router.delete("/{habit_id}")
async def delete_habit(
    habit_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a habit (set is_active=False)."""
    result = await db.execute(
        select(Habit).where(Habit.id == habit_id, Habit.user_id == current_user.id)
    )
    habit = result.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    habit.is_active = False
    await db.commit()
    return {"deleted": True, "habit_id": str(habit_id)}


@router.post("/{habit_id}/log", response_model=HabitLogResponse, status_code=status.HTTP_201_CREATED)
async def log_completion(
    habit_id: uuid.UUID,
    body: HabitLogCreate = HabitLogCreate(),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Log a habit completion."""
    result = await db.execute(
        select(Habit).where(Habit.id == habit_id, Habit.user_id == current_user.id)
    )
    habit = result.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    if not habit.is_active:
        raise HTTPException(status_code=400, detail="Cannot log inactive habit")

    log = HabitLog(
        habit_id=habit.id,
        user_id=current_user.id,
        completed_at=body.completed_at or datetime.now(timezone.utc),
        notes=body.notes,
        value=body.value,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    logger.info("Habit logged: user=%s habit=%s", current_user.id, habit.name)
    return HabitLogResponse(
        id=str(log.id),
        habit_id=str(log.habit_id),
        completed_at=log.completed_at.isoformat(),
        notes=log.notes,
        value=log.value,
    )


@router.delete("/{habit_id}/log/{log_id}")
async def undo_completion(
    habit_id: uuid.UUID,
    log_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Undo a habit completion (delete a log entry)."""
    result = await db.execute(
        select(HabitLog).where(
            HabitLog.id == log_id,
            HabitLog.habit_id == habit_id,
            HabitLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")

    await db.delete(log)
    await db.commit()
    return {"deleted": True, "log_id": str(log_id)}


@router.get("/{habit_id}/stats", response_model=HabitStatsResponse)
async def get_habit_stats(
    habit_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Get streak, completion rate (last 30 days), and history for a habit."""
    result = await db.execute(
        select(Habit).where(Habit.id == habit_id, Habit.user_id == current_user.id)
    )
    habit = result.scalar_one_or_none()
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    current_streak = await _calculate_streak(db, habit, current_user.id)
    longest_streak = await _calculate_longest_streak(db, habit, current_user.id)

    # Last 30 days completion data
    today = datetime.now(timezone.utc).date()
    thirty_days_ago = today - timedelta(days=30)
    day_start = datetime(
        thirty_days_ago.year, thirty_days_ago.month, thirty_days_ago.day,
        tzinfo=timezone.utc,
    )

    result = await db.execute(
        select(HabitLog.completed_at)
        .where(
            HabitLog.habit_id == habit.id,
            HabitLog.user_id == current_user.id,
            HabitLog.completed_at >= day_start,
        )
        .order_by(HabitLog.completed_at.asc())
    )
    recent_logs = result.scalars().all()

    # Group by date
    daily_counts: dict[str, int] = {}
    for completed_at in recent_logs:
        d = completed_at.date().isoformat()
        daily_counts[d] = daily_counts.get(d, 0) + 1

    # Build last 30 days array
    last_30: list[dict[str, Any]] = []
    applicable_days = 0
    completed_days = 0
    for days_back in range(30, -1, -1):
        check_date = today - timedelta(days=days_back)

        # Skip non-applicable days
        if habit.frequency == "weekday" and check_date.weekday() >= 5:
            continue
        if habit.frequency == "weekly" and check_date.weekday() != today.weekday():
            continue

        applicable_days += 1
        count = daily_counts.get(check_date.isoformat(), 0)
        if count >= habit.target_count:
            completed_days += 1

        last_30.append({"date": check_date.isoformat(), "count": count})

    completion_rate = completed_days / applicable_days if applicable_days > 0 else 0.0

    # Total completions
    total_result = await db.execute(
        select(func.count())
        .select_from(HabitLog)
        .where(HabitLog.habit_id == habit.id, HabitLog.user_id == current_user.id)
    )
    total_completions = total_result.scalar() or 0

    return HabitStatsResponse(
        habit_id=str(habit.id),
        habit_name=habit.name,
        current_streak=current_streak,
        longest_streak=longest_streak,
        completion_rate=round(completion_rate, 3),
        total_completions=total_completions,
        last_30_days=last_30,
    )


@router.get("/summary", response_model=HabitSummaryResponse)
async def get_habit_summary(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Get today's habit summary: how many done/total, streak info."""
    result = await db.execute(
        select(Habit)
        .where(Habit.user_id == current_user.id, Habit.is_active.is_(True))
        .order_by(Habit.sort_order.asc(), Habit.created_at.asc())
    )
    habits = result.scalars().all()

    habit_responses = []
    completed_today = 0
    total_today = 0

    for habit in habits:
        today_count = await _get_today_count(db, habit.id, current_user.id)
        streak = await _calculate_streak(db, habit, current_user.id)

        # Check if this habit applies today
        today_date = datetime.now(timezone.utc).date()
        applies_today = True
        if habit.frequency == "weekday" and today_date.weekday() >= 5:
            applies_today = False
        # Weekly habits always show, just might not be "due"

        if applies_today:
            total_today += 1
            if today_count >= habit.target_count:
                completed_today += 1

        d = _habit_to_dict(habit)
        d["today_count"] = today_count
        d["current_streak"] = streak
        habit_responses.append(HabitResponse(**d))

    pct = (completed_today / total_today * 100) if total_today > 0 else 0.0

    return HabitSummaryResponse(
        total_habits=len(habits),
        completed_today=completed_today,
        total_today=total_today,
        completion_percentage=round(pct, 1),
        habits=habit_responses,
    )
