"""Location history model — stores timestamped location entries for timeline display."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class LocationHistory(UUIDMixin, TimestampMixin, Base):
    """A single location data point in the user's travel timeline."""

    __tablename__ = "location_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_location_history_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<LocationHistory(id={self.id!r}, lat={self.latitude!r}, "
            f"lng={self.longitude!r}, city={self.city!r})>"
        )
