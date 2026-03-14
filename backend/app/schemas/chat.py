"""
Pydantic v2 schemas for the JARVIS chat system.

Covers conversation CRUD, message payloads, chat requests, and streaming
chunk envelopes used by both the SSE and WebSocket transports.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════════════
# Conversation schemas
# ═════════════════════════════════════════════════════════════════════════════


class ConversationCreate(BaseModel):
    """Payload for creating a new conversation."""

    title: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional title; auto-generated from the first message when omitted.",
    )
    model: Optional[str] = Field(
        "gpt-4o",
        max_length=64,
        description="LLM model identifier.",
    )
    system_prompt: Optional[str] = Field(
        None,
        description="System-level prompt prepended to every request in this conversation.",
    )


class ConversationUpdate(BaseModel):
    """Payload for updating an existing conversation."""

    title: Optional[str] = Field(None, max_length=255)
    model: Optional[str] = Field(None, max_length=64)
    system_prompt: Optional[str] = None
    is_archived: Optional[bool] = None


class ConversationResponse(BaseModel):
    """Public representation of a conversation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: Optional[str] = None
    model: str
    system_prompt: Optional[str] = None
    is_archived: bool
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata_: Optional[dict] = None


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""

    conversations: list[ConversationResponse]
    total: int


# ═════════════════════════════════════════════════════════════════════════════
# Message schemas
# ═════════════════════════════════════════════════════════════════════════════


class MessageCreate(BaseModel):
    """Payload for adding a single message to a conversation."""

    content: str = Field(..., min_length=1, description="Message body.")
    role: str = Field(
        "user",
        pattern=r"^(user|assistant|system|tool)$",
        description="Message role.",
    )


class MessageResponse(BaseModel):
    """Public representation of a message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    token_count: Optional[int] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    tool_calls: Optional[Any] = None
    created_at: datetime


# ═════════════════════════════════════════════════════════════════════════════
# Chat request / streaming schemas
# ═════════════════════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """
    Unified request body accepted by the REST, SSE, and WebSocket chat
    endpoints.  When *conversation_id* is omitted a new conversation is
    created automatically.
    """

    message: str = Field(..., min_length=1, description="User message text.")
    conversation_id: Optional[uuid.UUID] = Field(
        None,
        description="Existing conversation to continue; omit to start a new one.",
    )
    model: Optional[str] = Field(
        None,
        max_length=64,
        description="Override the conversation's default model for this turn.",
    )
    stream: bool = Field(
        True,
        description="Whether to stream the response. Ignored by the non-streaming endpoint.",
    )
    system_prompt: Optional[str] = Field(
        None,
        description="Override system prompt for this turn only.",
    )
    model_provider: Optional[str] = Field(
        None,
        max_length=32,
        description="LLM provider to use: claude, gemini, or stark_protocol.",
    )
    voice_enabled: bool = Field(
        False,
        description="Synthesize audio response via ElevenLabs.",
    )


class ChatStreamChunk(BaseModel):
    """
    Envelope for a single chunk emitted during streaming.

    *type* values:
    - ``"start"``        — first chunk, carries *conversation_id* and *message_id*.
    - ``"token"``        — incremental content token.
    - ``"end"``          — final chunk; *done* is ``True``.
    - ``"error"``        — an error occurred; *error* contains the description.
    - ``"tool_call"``    — Claude is invoking a tool; *tool* and *tool_arg* are set.
    - ``"tool_result"``  — tool execution result; *tool* and *content* are set.
    - ``"replace"``      — replace the full response text (after stripping tags).
    """

    type: str = Field(
        ...,
        description='Chunk type: "start", "token", "end", "error", "tool_call", "tool_result", or "replace".',
    )
    content: Optional[str] = Field(None, description="Token content for type=token, or tool result for type=tool_result.")
    conversation_id: Optional[uuid.UUID] = Field(
        None,
        description="Set on the start chunk so the client knows the conversation.",
    )
    message_id: Optional[uuid.UUID] = Field(
        None,
        description="Set on the start chunk; ID of the assistant message being built.",
    )
    done: Optional[bool] = Field(None, description="True on the end chunk.")
    error: Optional[str] = Field(None, description="Error description when type=error.")
    tool: Optional[str] = Field(None, description="Tool name for type=tool_call or tool_result.")
    tool_arg: Optional[str] = Field(None, description="Tool input JSON for type=tool_call.")
