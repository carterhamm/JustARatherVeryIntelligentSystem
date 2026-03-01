"""
Lightweight fallback TTS client using edge-tts.

When the primary ElevenLabs service is unavailable (API key missing,
quota exhausted, network issues), this module provides a zero-cost
text-to-speech alternative using Microsoft Edge's online TTS service
via the ``edge-tts`` library.  If that is also unavailable, it falls
back to ``gTTS`` (Google Translate TTS).
"""

from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger("jarvis.tts_fallback")

# Default edge-tts voice -- a clear British-English male voice that
# works well as a JARVIS-style assistant.
_DEFAULT_EDGE_VOICE = "en-GB-RyanNeural"

# Fallback gTTS language
_DEFAULT_GTTS_LANG = "en"


class CoquiTTSClient:
    """
    Fallback TTS client that does *not* require an API key.

    Despite the name (kept for backward-compatibility with the service
    layer), this client tries the following backends in order:

    1. **edge-tts** -- Microsoft Edge neural voices (free, high quality).
    2. **gTTS**     -- Google Translate TTS (free, acceptable quality).
    3. Raises :class:`RuntimeError` if neither is available.
    """

    def __init__(self, default_voice: str = _DEFAULT_EDGE_VOICE) -> None:
        self._default_voice = default_voice
        self._backend: Optional[str] = None
        self._resolve_backend()

    # ── Public API ───────────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize *text* into MP3 audio bytes.

        Parameters
        ----------
        text:
            The text to speak.
        speaker:
            Voice / speaker name.  Interpretation depends on the active
            backend.  For *edge-tts* this is a voice short-name such as
            ``"en-GB-RyanNeural"``.  Ignored for *gTTS*.

        Returns
        -------
        bytes
            Raw MP3 audio data.
        """
        if self._backend == "edge-tts":
            return await self._synthesize_edge(text, speaker)
        if self._backend == "gtts":
            return await self._synthesize_gtts(text)
        raise RuntimeError(
            "No fallback TTS backend available. "
            "Install 'edge-tts' (`pip install edge-tts`) or "
            "'gTTS' (`pip install gTTS`)."
        )

    # ── Backend implementations ──────────────────────────────────────────

    async def _synthesize_edge(self, text: str, speaker: Optional[str]) -> bytes:
        """Use the *edge-tts* library for synthesis."""
        import edge_tts  # type: ignore[import-untyped]

        voice = speaker or self._default_voice
        communicate = edge_tts.Communicate(text, voice)

        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])

        audio_bytes = buffer.getvalue()
        if not audio_bytes:
            raise RuntimeError("edge-tts returned empty audio")
        return audio_bytes

    async def _synthesize_gtts(self, text: str) -> bytes:
        """
        Use *gTTS* for synthesis.

        gTTS is synchronous, so we run it in the default executor to avoid
        blocking the event loop.
        """
        import asyncio
        from functools import partial

        from gtts import gTTS  # type: ignore[import-untyped]

        def _generate() -> bytes:
            tts = gTTS(text=text, lang=_DEFAULT_GTTS_LANG)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            return buf.getvalue()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(_generate))

    # ── Internals ────────────────────────────────────────────────────────

    def _resolve_backend(self) -> None:
        """Detect which TTS backend is importable."""
        try:
            import edge_tts  # noqa: F401
            self._backend = "edge-tts"
            logger.info("Fallback TTS backend: edge-tts")
            return
        except ImportError:
            pass

        try:
            import gtts  # noqa: F401
            self._backend = "gtts"
            logger.info("Fallback TTS backend: gTTS")
            return
        except ImportError:
            pass

        self._backend = None
        logger.warning(
            "No fallback TTS backend found. Install 'edge-tts' or 'gTTS'."
        )
