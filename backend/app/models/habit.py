"""
Habit tracking SQLAlchemy models for J.A.R.V.I.S.

Stores user habits and completion logs for streak tracking,
daily/weekly goals, and progress monitoring.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Habit(UUIDMixin, TimestampMixin, Base):
    """A trackable habit belonging to a user."""

    __tablename__ = "habits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    frequency: Mapped[str] = mapped_column(
        String(32), nullable=False, default="daily",
    )
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    icon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")
    logs: Mapped[list["HabitLog"]] = relationship(
        "HabitLog", back_populates="habit", lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Habit(id={self.id!r}, name={self.name!r}, "
            f"frequency={self.frequency!r}, user_id={self.user_id!r})>"
        )


class HabitLog(UUIDMixin, TimestampMixin, Base):
    """A single completion log entry for a habit."""

    __tablename__ = "habit_logs"

    habit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("habits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Relationships
    habit: Mapped["Habit"] = relationship("Habit", back_populates="logs")
    user: Mapped["User"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<HabitLog(id={self.id!r}, habit_id={self.habit_id!r}, "
            f"completed_at={self.completed_at!r})>"
        )
