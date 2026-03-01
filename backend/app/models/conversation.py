"""
Conversation and Message SQLAlchemy models for the JARVIS chat system.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User


class Conversation(UUIDMixin, TimestampMixin, Base):
    """
    Represents a chat conversation between a user and the JARVIS assistant.

    Each conversation contains an ordered sequence of messages and tracks
    metadata such as the LLM model in use, system prompt, archival status,
    and aggregate statistics (message count, last activity).
    """

    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Auto-generated from the first user message if not provided.",
    )
    model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="gpt-4o",
        server_default="gpt-4o",
    )
    system_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=None,
    )

    # ── Relationships ────────────────────────────────────────────────────
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="conversations",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation(id={self.id!r}, user_id={self.user_id!r}, "
            f"title={self.title!r}, model={self.model!r})>"
        )


class Message(UUIDMixin, Base):
    """
    A single message within a conversation.

    Messages can originate from the user, the assistant, the system prompt,
    or a tool-call result.  Each message optionally records token usage,
    model identity, and response latency for observability.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc='One of "user", "assistant", "system", or "tool".',
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    model: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    tool_calls: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=None,
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
    )

    # ── Relationships ────────────────────────────────────────────────────
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        snippet = (self.content[:40] + "...") if len(self.content) > 40 else self.content
        return (
            f"<Message(id={self.id!r}, role={self.role!r}, "
            f"content={snippet!r})>"
        )
