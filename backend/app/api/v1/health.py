"""
Health Data API — sync, query, and summarise health samples from Apple HealthKit.

The JARVIS iOS app pushes HealthKit data here in batches. Samples are
deduplicated by (user_id, sample_type, start_date, end_date) so the same
sync payload can be retried safely.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_or_service, get_db
from app.models.health import HealthSample
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


# ── Schemas ──────────────────────────────────────────────────────────────

class HealthSampleIn(BaseModel):
    sample_type: str = Field(..., description="e.g. steps, heart_rate, sleep, workout")
    value: float
    unit: str = Field(..., description="e.g. count, bpm, hours, kcal")
    start_date: datetime
    end_date: datetime
    source_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class SyncRequest(BaseModel):
    samples: list[HealthSampleIn]


class SyncResponse(BaseModel):
    inserted: int
    skipped: int
    message: str


class HealthSampleOut(BaseModel):
    id: str
    sample_type: str
    value: float
    unit: str
    start_date: str
    end_date: str
    source_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class HealthSummaryResponse(BaseModel):
    date: str
    steps: Optional[dict[str, Any]] = None
    heart_rate: Optional[dict[str, Any]] = None
    sleep: Optional[dict[str, Any]] = None
    workouts: list[dict[str, Any]] = []


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/sync", response_model=SyncResponse)
async def sync_health_data(
    body: SyncRequest,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Accept a batch of health samples from the iOS app.

    Deduplicates by (user_id, sample_type, start_date, end_date) using
    ON CONFLICT DO NOTHING so re-syncs are safe.
    """
    if not body.samples:
        return SyncResponse(inserted=0, skipped=0, message="No samples provided.")

    inserted = 0
    skipped = 0

    for sample in body.samples:
        meta_str = json.dumps(sample.metadata) if sample.metadata else None
        stmt = (
            pg_insert(HealthSample)
            .values(
                user_id=current_user.id,
                sample_type=sample.sample_type,
                value=sample.value,
                unit=sample.unit,
                start_date=sample.start_date,
                end_date=sample.end_date,
                source_name=sample.source_name,
                metadata_json=meta_str,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "sample_type", "start_date", "end_date"],
            )
        )
        result = await db.execute(stmt)
        if result.rowcount > 0:
            inserted += 1
        else:
            skipped += 1

    await db.commit()

    logger.info(
        "Health sync: user=%s inserted=%d skipped=%d total=%d",
        current_user.id, inserted, skipped, len(body.samples),
    )
    return SyncResponse(
        inserted=inserted,
        skipped=skipped,
        message=f"Synced {inserted} new samples, {skipped} duplicates skipped.",
    )


@router.get("/summary", response_model=HealthSummaryResponse)
async def health_summary(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Return a summary of today's health data.

    - Today's total steps
    - Most recent heart rate reading
    - Last night's total sleep
    - Recent workouts (last 7 days)
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_ago = today_start - timedelta(days=7)

    summary: dict[str, Any] = {"date": today_start.date().isoformat()}

    # ── Steps today (sum) ────────────────────────────────────────────
    steps_result = await db.execute(
        select(func.sum(HealthSample.value))
        .where(
            HealthSample.user_id == current_user.id,
            HealthSample.sample_type == "steps",
            HealthSample.start_date >= today_start,
        )
    )
    steps_total = steps_result.scalar()
    if steps_total is not None:
        summary["steps"] = {"total": round(steps_total), "unit": "count"}

    # ── Heart rate (most recent) ─────────────────────────────────────
    hr_result = await db.execute(
        select(HealthSample)
        .where(
            HealthSample.user_id == current_user.id,
            HealthSample.sample_type == "heart_rate",
        )
        .order_by(HealthSample.start_date.desc())
        .limit(1)
    )
    hr_sample = hr_result.scalar_one_or_none()
    if hr_sample:
        summary["heart_rate"] = {
            "value": round(hr_sample.value),
            "unit": hr_sample.unit,
            "recorded_at": hr_sample.start_date.isoformat(),
        }

    # ── Sleep last night (sum of sleep samples from yesterday evening to now)
    sleep_result = await db.execute(
        select(func.sum(HealthSample.value))
        .where(
            HealthSample.user_id == current_user.id,
            HealthSample.sample_type == "sleep",
            HealthSample.start_date >= yesterday_start,
            HealthSample.start_date < today_start + timedelta(hours=12),
        )
    )
    sleep_total = sleep_result.scalar()
    if sleep_total is not None:
        summary["sleep"] = {"total_hours": round(sleep_total, 1), "unit": "hours"}

    # ── Workouts (last 7 days) ───────────────────────────────────────
    workout_result = await db.execute(
        select(HealthSample)
        .where(
            HealthSample.user_id == current_user.id,
            HealthSample.sample_type == "workout",
            HealthSample.start_date >= week_ago,
        )
        .order_by(HealthSample.start_date.desc())
        .limit(10)
    )
    workouts = workout_result.scalars().all()
    workout_list = []
    for w in workouts:
        entry: dict[str, Any] = {
            "value": round(w.value, 1),
            "unit": w.unit,
            "start": w.start_date.isoformat(),
            "end": w.end_date.isoformat(),
        }
        if w.source_name:
            entry["source"] = w.source_name
        if w.metadata_json:
            try:
                entry["details"] = json.loads(w.metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
        workout_list.append(entry)
    summary["workouts"] = workout_list

    return HealthSummaryResponse(**summary)


@router.get("/history", response_model=list[HealthSampleOut])
async def health_history(
    sample_type: str = Query(..., description="Type of health data (e.g. steps, heart_rate, sleep, workout)"),
    start: Optional[str] = Query(None, description="Start date/time in ISO format"),
    end: Optional[str] = Query(None, description="End date/time in ISO format"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Query health data by type and optional date range."""
    conditions = [
        HealthSample.user_id == current_user.id,
        HealthSample.sample_type == sample_type,
    ]

    if start:
        try:
            start_dt = datetime.fromisoformat(start)
            conditions.append(HealthSample.start_date >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start date format. Use ISO 8601.",
            )

    if end:
        try:
            end_dt = datetime.fromisoformat(end)
            conditions.append(HealthSample.end_date <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end date format. Use ISO 8601.",
            )

    result = await db.execute(
        select(HealthSample)
        .where(and_(*conditions))
        .order_by(HealthSample.start_date.desc())
        .limit(limit)
    )
    samples = result.scalars().all()

    out = []
    for s in samples:
        meta = None
        if s.metadata_json:
            try:
                meta = json.loads(s.metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(HealthSampleOut(
            id=str(s.id),
            sample_type=s.sample_type,
            value=s.value,
            unit=s.unit,
            start_date=s.start_date.isoformat(),
            end_date=s.end_date.isoformat(),
            source_name=s.source_name,
            metadata=meta,
        ))
    return out
