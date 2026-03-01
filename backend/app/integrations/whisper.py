"""
Async Whisper STT client wrapping the OpenAI Whisper API.

Provides transcription of audio data in various formats (wav, mp3, m4a, webm)
using OpenAI's whisper-1 model with automatic retry and structured results.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)

logger = logging.getLogger("jarvis.whisper")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Supported audio MIME types mapped from file extension
_MIME_TYPES: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
}


@dataclass
class TranscriptionSegment:
    """A single timed segment within a transcription."""

    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    """Structured result returned by the Whisper transcription API."""

    text: str
    language: str
    duration: float
    segments: list[TranscriptionSegment] = field(default_factory=list)


class WhisperClient:
    """
    Async client for OpenAI's Whisper speech-to-text API.

    Supports transcription of raw audio bytes or files on disk, with
    automatic retries for transient network / rate-limit errors.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            max_retries=max_retries,
            timeout=120.0,
        )
        self._model = model
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    # ── Public API ───────────────────────────────────────────────────────

    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        format: str = "wav",
    ) -> TranscriptionResult:
        """
        Transcribe raw audio bytes using the Whisper API.

        Parameters
        ----------
        audio_data:
            Raw audio bytes in the specified *format*.
        language:
            Optional ISO-639-1 language hint (e.g. ``"en"``).
        format:
            Audio format / file extension. Defaults to ``"wav"``.

        Returns
        -------
        TranscriptionResult
            Structured transcription with text, language, duration, and
            timed segments.
        """
        import asyncio

        # Wrap bytes in a file-like object with a proper filename so the
        # API can infer the content type.
        ext = format.lower().lstrip(".")
        mime = _MIME_TYPES.get(ext, "application/octet-stream")
        filename = f"audio.{ext}"
        audio_file = (filename, io.BytesIO(audio_data), mime)

        kwargs: dict = {
            "model": self._model,
            "file": audio_file,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
        }
        if language:
            kwargs["language"] = language

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                # Reset the BytesIO position for each retry
                audio_file[1].seek(0)

                response = await self._client.audio.transcriptions.create(**kwargs)
                return self._parse_response(response)
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2 ** attempt)
                logger.warning(
                    "Whisper request failed (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    self._max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Whisper transcription failed after {self._max_retries} retries"
        ) from last_exc

    async def transcribe_file(
        self,
        file_path: str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file from disk.

        The audio format is inferred from the file extension.

        Parameters
        ----------
        file_path:
            Path to the audio file.
        language:
            Optional ISO-639-1 language hint.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        ext = path.suffix.lstrip(".")
        if ext not in _MIME_TYPES:
            raise ValueError(
                f"Unsupported audio format '{ext}'. "
                f"Supported: {', '.join(sorted(_MIME_TYPES))}"
            )

        audio_data = path.read_bytes()
        return await self.transcribe(audio_data, language=language, format=ext)

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(response: object) -> TranscriptionResult:
        """
        Parse the verbose JSON response from the Whisper API into a
        :class:`TranscriptionResult`.
        """
        # The response object has attributes when using verbose_json
        text: str = getattr(response, "text", "") or ""
        language: str = getattr(response, "language", "unknown") or "unknown"
        duration: float = getattr(response, "duration", 0.0) or 0.0
        raw_segments: list = getattr(response, "segments", None) or []

        segments: list[TranscriptionSegment] = []
        for seg in raw_segments:
            if isinstance(seg, dict):
                segments.append(
                    TranscriptionSegment(
                        start=float(seg.get("start", 0.0)),
                        end=float(seg.get("end", 0.0)),
                        text=seg.get("text", "").strip(),
                    )
                )
            else:
                # Pydantic-style object from the OpenAI SDK
                segments.append(
                    TranscriptionSegment(
                        start=float(getattr(seg, "start", 0.0)),
                        end=float(getattr(seg, "end", 0.0)),
                        text=getattr(seg, "text", "").strip(),
                    )
                )

        return TranscriptionResult(
            text=text.strip(),
            language=language,
            duration=duration,
            segments=segments,
        )
