"""PasskeyCredential ORM model for WebAuthn / FIDO2 credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class PasskeyCredential(UUIDMixin, TimestampMixin, Base):
    """A WebAuthn credential belonging to a user."""

    __tablename__ = "passkey_credentials"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    transports: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="passkeys", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PasskeyCredential id={self.id} user_id={self.user_id}>"
