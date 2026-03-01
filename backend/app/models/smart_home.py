"""
Smart home SQLAlchemy models for J.A.R.V.I.S.

Tracks registered smart-home devices, user-defined scenes, and device
event history.
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
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SmartDevice(Base):
    """A smart-home device registered by the user.

    Devices are discovered via the Matter protocol (or other bridges)
    and synced into this table.  The ``state`` column stores the
    last-known device state as a JSON blob (e.g.
    ``{"on": true, "brightness": 80}``).
    """

    __tablename__ = "smart_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        doc="External device ID assigned by the smart-home controller.",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    device_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc='One of "light", "switch", "thermostat", "lock", "sensor", "speaker", "camera".',
    )
    room: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    state: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )
    is_online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ── Relationships ────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", lazy="selectin")
    events: Mapped[list["DeviceEvent"]] = relationship(
        "DeviceEvent",
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="DeviceEvent.created_at.desc()",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<SmartDevice(id={self.id!r}, name={self.name!r}, "
            f"type={self.device_type!r}, room={self.room!r})>"
        )


class SmartScene(Base):
    """A user-defined scene that bundles multiple device actions.

    Activating a scene sends the specified commands to each device
    in the ``devices`` list.  Example ``devices`` value::

        [
            {"device_id": "abc-123", "command": "on", "params": {"brightness": 50}},
            {"device_id": "def-456", "command": "set_temperature", "params": {"temperature": 22}}
        ]
    """

    __tablename__ = "smart_scenes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    devices: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        doc="JSON array of device actions.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ── Relationships ────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<SmartScene(id={self.id!r}, name={self.name!r}, "
            f"is_active={self.is_active!r})>"
        )


class DeviceEvent(Base):
    """An event recorded for a smart-home device (state change, alert, etc.)."""

    __tablename__ = "device_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("smart_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc='E.g. "state_change", "command", "alert", "offline", "online".',
    )
    data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )

    # ── Relationships ────────────────────────────────────────────────
    device: Mapped["SmartDevice"] = relationship(
        "SmartDevice",
        back_populates="events",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceEvent(id={self.id!r}, device_id={self.device_id!r}, "
            f"event_type={self.event_type!r})>"
        )
