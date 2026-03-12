"""
Health sample SQLAlchemy model for J.A.R.V.I.S.

Stores health data synced from the JARVIS iOS app (Apple HealthKit).
Fields are NOT encrypted — they must be queryable for the health_summary tool.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class HealthSample(UUIDMixin, TimestampMixin, Base):
    """A single health data sample synced from Apple HealthKit."""

    __tablename__ = "health_samples"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sample_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(
        "metadata", Text, nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")

    # Composite index for deduplication: (user_id, sample_type, start_date, end_date)
    __table_args__ = (
        Index(
            "ix_health_samples_dedup",
            "user_id", "sample_type", "start_date", "end_date",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<HealthSample(id={self.id!r}, type={self.sample_type!r}, "
            f"value={self.value}, user_id={self.user_id!r})>"
        )
