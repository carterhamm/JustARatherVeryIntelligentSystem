"""
Pydantic v2 schemas for the JARVIS voice system.

Covers transcription (STT), synthesis (TTS), full voice-chat pipeline,
and voice listing.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════════════
# Transcription (STT) schemas
# ═════════════════════════════════════════════════════════════════════════════


class TranscribeRequest(BaseModel):
    """
    Describes the expected multipart form-data payload for transcription.

    The actual audio file is received via ``UploadFile`` in the endpoint;
    this schema documents the optional companion fields.
    """

    language: Optional[str] = Field(
        None,
        max_length=10,
        description="ISO-639-1 language hint (e.g. 'en'). Auto-detected when omitted.",
    )
    format: str = Field(
        "wav",
        max_length=10,
        description="Audio format of the uploaded file (wav, mp3, m4a, webm).",
    )


class TranscriptionSegment(BaseModel):
    """A single timed segment within a transcription."""

    start: float = Field(..., description="Segment start time in seconds.")
    end: float = Field(..., description="Segment end time in seconds.")
    text: str = Field(..., description="Transcribed text for this segment.")


class TranscribeResponse(BaseModel):
    """Transcription result returned by the STT endpoint."""

    model_config = ConfigDict(from_attributes=True)

    text: str = Field(..., description="Full transcribed text.")
    language: str = Field(..., description="Detected or specified language code.")
    duration: float = Field(..., description="Audio duration in seconds.")
    segments: list[TranscriptionSegment] = Field(
        default_factory=list,
        description="Timed segments with per-segment text.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Synthesis (TTS) schemas
# ═════════════════════════════════════════════════════════════════════════════


class SynthesizeRequest(BaseModel):
    """Request body for text-to-speech synthesis."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Text to synthesize into speech.",
    )
    voice_id: Optional[str] = Field(
        None,
        max_length=64,
        description="ElevenLabs voice ID. Uses the default JARVIS voice when omitted.",
    )
    model: Optional[str] = Field(
        None,
        max_length=64,
        description="TTS model identifier (e.g. 'eleven_multilingual_v2').",
    )
    output_format: str = Field(
        "mp3",
        max_length=20,
        description="Desired output audio format (mp3, wav, ogg).",
    )


class SynthesizeResponse(BaseModel):
    """
    Metadata schema describing a synthesis result.

    The actual audio bytes are returned as a ``StreamingResponse`` with an
    appropriate ``Content-Type`` header; this schema is used only in OpenAPI
    documentation and error envelopes.
    """

    content_type: str = Field(
        "audio/mpeg",
        description="MIME type of the returned audio.",
    )
    size_bytes: Optional[int] = Field(
        None,
        description="Size of the audio payload in bytes (when known).",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Voice Chat (full pipeline) schemas
# ═════════════════════════════════════════════════════════════════════════════


class VoiceChatRequest(BaseModel):
    """
    Describes the multipart payload for the voice-chat endpoint.

    The audio file itself is received as an ``UploadFile``; this schema
    documents the optional JSON fields sent alongside it.
    """

    conversation_id: Optional[uuid.UUID] = Field(
        None,
        description="Existing conversation to continue; omit to start a new one.",
    )
    model: Optional[str] = Field(
        None,
        max_length=64,
        description="Override LLM model for the chat turn.",
    )


class VoiceChatResponse(BaseModel):
    """Response from the full voice-chat pipeline."""

    model_config = ConfigDict(from_attributes=True)

    transcription: str = Field(
        ..., description="Transcribed text from the user's audio."
    )
    response_text: str = Field(
        ..., description="Assistant's text response."
    )
    audio_url: Optional[str] = Field(
        None,
        description="URL to the synthesized audio response (when available).",
    )
    conversation_id: uuid.UUID = Field(
        ..., description="Conversation ID (existing or newly created)."
    )


# ═════════════════════════════════════════════════════════════════════════════
# Voice listing
# ═════════════════════════════════════════════════════════════════════════════


class VoiceInfo(BaseModel):
    """Summary of a single available voice."""

    voice_id: str
    name: str
    category: Optional[str] = None
    labels: dict[str, Any] = Field(default_factory=dict)
    preview_url: Optional[str] = None


class VoiceListResponse(BaseModel):
    """List of available TTS voices."""

    voices: list[VoiceInfo] = Field(
        default_factory=list,
        description="Available voices for synthesis.",
    )
