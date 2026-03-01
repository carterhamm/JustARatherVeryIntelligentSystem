"""
Async ElevenLabs TTS client.

Provides text-to-speech synthesis using the ElevenLabs API with support for
synchronous full-audio responses and streaming audio generation.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Optional

import httpx

logger = logging.getLogger("jarvis.elevenlabs")

_BASE_URL = "https://api.elevenlabs.io/v1"

# A deep, clear, authoritative male voice suitable for a JARVIS-style assistant.
# This maps to "Daniel" on ElevenLabs -- swap the ID for any voice you prefer.
_DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"

_DEFAULT_MODEL = "eleven_multilingual_v2"

_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class ElevenLabsClient:
    """
    Async client for the ElevenLabs text-to-speech API.

    Uses *httpx* for all HTTP communication so it integrates cleanly with
    asyncio-based servers such as FastAPI / Uvicorn.
    """

    def __init__(
        self,
        api_key: str,
        default_voice_id: str = _DEFAULT_VOICE_ID,
        default_model: str = _DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._default_voice_id = default_voice_id
        self._default_model = default_model
        self._http = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "xi-api-key": api_key,
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
    ) -> bytes:
        """
        Synthesize *text* into audio and return the full audio as bytes.

        Parameters
        ----------
        text:
            The text to convert to speech.
        voice_id:
            ElevenLabs voice identifier. Falls back to the default
            JARVIS-style voice.
        model:
            Model identifier (e.g. ``"eleven_multilingual_v2"``).
        output_format:
            Audio output format string accepted by ElevenLabs.

        Returns
        -------
        bytes
            Raw audio data (MP3 by default).
        """
        vid = voice_id or self._default_voice_id
        url = f"/text-to-speech/{vid}"

        payload: dict[str, Any] = {
            "text": text,
            "model_id": model or self._default_model,
            "voice_settings": self._default_voice_settings(),
        }

        response = await self._http.post(
            url,
            json=payload,
            params={"output_format": output_format},
            headers={"Accept": "audio/mpeg"},
        )
        response.raise_for_status()
        return response.content

    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized audio chunks for *text*.

        Yields
        ------
        bytes
            Sequential audio data chunks. The consumer can write them
            directly to a streaming HTTP response or WebSocket.
        """
        vid = voice_id or self._default_voice_id
        url = f"/text-to-speech/{vid}/stream"

        payload: dict[str, Any] = {
            "text": text,
            "model_id": model or self._default_model,
            "voice_settings": self._default_voice_settings(),
        }

        async with self._http.stream(
            "POST",
            url,
            json=payload,
            params={"output_format": output_format},
            headers={"Accept": "audio/mpeg"},
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=4096):
                yield chunk

    async def list_voices(self) -> list[dict[str, Any]]:
        """
        Retrieve all voices available on the account.

        Returns
        -------
        list[dict]
            Each dict contains at minimum ``voice_id``, ``name``, and
            ``labels``.
        """
        response = await self._http.get("/voices")
        response.raise_for_status()
        data = response.json()
        return data.get("voices", [])

    async def get_voice(self, voice_id: str) -> dict[str, Any]:
        """
        Retrieve metadata for a single voice.
        """
        response = await self._http.get(f"/voices/{voice_id}")
        response.raise_for_status()
        return response.json()

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _default_voice_settings() -> dict[str, float]:
        """
        Return the default voice settings tuned for a JARVIS-style
        assistant: clear, stable, with a touch of expressiveness.
        """
        return {
            "stability": 0.60,
            "similarity_boost": 0.80,
            "style": 0.15,
            "use_speaker_boost": True,
        }

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "ElevenLabsClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
