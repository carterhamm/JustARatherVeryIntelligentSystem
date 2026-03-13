"""
Landmark / saved-place SQLAlchemy model for J.A.R.V.I.S.

Stores user-pinned places on the map with coordinates, description,
and optional Apple Maps link.  Fields are NOT encrypted because they
need to be queryable for map display.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Landmark(UUIDMixin, TimestampMixin, Base):
    """A user-saved place / landmark with map coordinates."""

    __tablename__ = "landmarks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    apple_maps_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="pin")
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, default="#f0a500")

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Landmark(id={self.id!r}, name={self.name!r}, "
            f"lat={self.latitude!r}, lng={self.longitude!r}, "
            f"user_id={self.user_id!r})>"
        )
