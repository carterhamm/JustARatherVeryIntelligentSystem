"""
Reminder SQLAlchemy model for J.A.R.V.I.S.

Stores user-created reminders that are scheduled to fire at a specified
time.  The agent tool layer persists reminders here so they survive
server restarts and can be picked up by a background scheduler.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Reminder(UUIDMixin, TimestampMixin, Base):
    """A scheduled reminder for a user.

    The ``remind_at`` column stores the UTC datetime when the reminder
    should fire.  A background worker (e.g. APScheduler, Celery beat)
    queries for due reminders and delivers notifications.
    """

    __tablename__ = "reminders"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    remind_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    is_delivered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        doc="Conversation in which the reminder was created, for context.",
    )

    # ── Relationships ────────────────────────────────────────────────
    user: Mapped[Optional["User"]] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Reminder(id={self.id!r}, message={self.message[:40]!r}, "
            f"remind_at={self.remind_at!r}, is_delivered={self.is_delivered!r})>"
        )
