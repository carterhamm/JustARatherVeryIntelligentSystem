"""
FocusSession SQLAlchemy model for J.A.R.V.I.S.

Stores deep work and focused learning sessions with duration, ratings,
distraction counts, and notes. Fields are NOT encrypted — they must be
queryable for the focus_session tool stats aggregations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class FocusSession(UUIDMixin, TimestampMixin, Base):
    """A single deep work or focused learning session."""

    __tablename__ = "focus_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(256), nullable=False,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    planned_duration_min: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    actual_duration_min: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    distractions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    energy_level: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    productivity_rating: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")

    # Index for per-user time-ordered queries
    __table_args__ = (
        Index(
            "ix_focus_sessions_user_started",
            "user_id", "started_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FocusSession(id={self.id!r}, title={self.title!r}, "
            f"category={self.category!r}, user_id={self.user_id!r})>"
        )
