"""User session model — tracks login sessions with device/IP/location info."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Session(UUIDMixin, TimestampMixin, Base):
    """A tracked login session with device, IP, and activity metadata."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    location_city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    location_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    signed_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    login_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Session(id={self.id!r}, user_id={self.user_id!r}, "
            f"device={self.device_type!r}, active={self.is_active!r})>"
        )
