"""
JARVIS Voice Service.

Orchestrates the full voice pipeline: speech-to-text (Whisper),
text-to-speech (ElevenLabs / fallback), and the end-to-end voice-chat
loop that chains STT -> LLM chat -> TTS.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Any, AsyncGenerator, Optional

from app.integrations.elevenlabs import ElevenLabsClient
from app.integrations.tts_fallback import CoquiTTSClient
from app.integrations.whisper import WhisperClient
from app.schemas.voice import (
    TranscribeResponse,
    TranscriptionSegment,
    VoiceChatResponse,
    VoiceInfo,
)

logger = logging.getLogger("jarvis.voice_service")


class VoiceService:
    """
    High-level voice service that composes the STT and TTS integration
    clients into a unified interface.

    Parameters
    ----------
    whisper:
        Whisper STT client for audio transcription.
    elevenlabs:
        ElevenLabs TTS client (primary).
    chat_service:
        Optional chat / LLM service for the voice-chat pipeline.  When
        provided, transcribed user audio is sent through the chat service
        to generate an assistant response.  Any object with an async
        ``send_message(user_id, text, conversation_id)`` method will work.
    fallback_tts:
        Optional fallback TTS client used when ElevenLabs is unavailable.
    """

    def __init__(
        self,
        whisper: WhisperClient,
        elevenlabs: ElevenLabsClient,
        chat_service: Any = None,
        fallback_tts: Optional[CoquiTTSClient] = None,
    ) -> None:
        self._whisper = whisper
        self._elevenlabs = elevenlabs
        self._chat_service = chat_service
        self._fallback_tts = fallback_tts or CoquiTTSClient()

    # ── Transcription (STT) ──────────────────────────────────────────────

    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        format: str = "wav",
    ) -> TranscribeResponse:
        """
        Transcribe raw audio bytes and return a structured response.

        Parameters
        ----------
        audio_data:
            Raw audio bytes.
        language:
            Optional ISO-639-1 language hint.
        format:
            Audio format (wav, mp3, m4a, webm).
        """
        result = await self._whisper.transcribe(
            audio_data,
            language=language,
            format=format,
        )

        segments = [
            TranscriptionSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
            )
            for seg in result.segments
        ]

        return TranscribeResponse(
            text=result.text,
            language=result.language,
            duration=result.duration,
            segments=segments,
        )

    # ── Synthesis (TTS) ──────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize text to audio bytes.

        Tries ElevenLabs first; falls back to the CoquiTTS / edge-tts
        client on failure.

        Returns
        -------
        bytes
            Raw audio data (MP3).
        """
        try:
            audio = await self._elevenlabs.synthesize(
                text=text,
                voice_id=voice_id,
                model=model,
            )
            logger.debug("Synthesized %d bytes via ElevenLabs", len(audio))
            return audio
        except Exception as exc:
            logger.warning(
                "ElevenLabs synthesis failed (%s); falling back to edge-tts",
                exc,
            )
            audio = await self._fallback_tts.synthesize(text)
            logger.debug("Synthesized %d bytes via fallback TTS", len(audio))
            return audio

    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesized audio chunks from ElevenLabs.

        Falls back to a single-chunk response via the fallback TTS client
        if ElevenLabs streaming fails.
        """
        try:
            async for chunk in self._elevenlabs.synthesize_stream(
                text=text,
                voice_id=voice_id,
            ):
                yield chunk
        except Exception as exc:
            logger.warning(
                "ElevenLabs streaming failed (%s); falling back to single-shot",
                exc,
            )
            audio = await self._fallback_tts.synthesize(text)
            yield audio

    # ── Voice Chat (full pipeline) ───────────────────────────────────────

    async def voice_chat(
        self,
        user_id: str,
        audio_data: bytes,
        conversation_id: Optional[uuid_mod.UUID] = None,
        language: Optional[str] = None,
        format: str = "wav",
    ) -> VoiceChatResponse:
        """
        End-to-end voice chat pipeline:

        1. Transcribe the user's audio to text (Whisper).
        2. Send the text through the chat service (if available).
        3. Synthesize the assistant's text response to audio (ElevenLabs).
        4. Return the full result.

        Parameters
        ----------
        user_id:
            Authenticated user identifier.
        audio_data:
            Raw audio bytes from the user.
        conversation_id:
            Existing conversation to continue (optional).
        language:
            Language hint for STT.
        format:
            Audio format of the incoming audio.
        """
        # Step 1: Transcribe
        transcription = await self.transcribe(
            audio_data, language=language, format=format
        )
        user_text = transcription.text

        logger.info(
            "Voice chat transcription for user %s: '%s'",
            user_id,
            user_text[:100],
        )

        # Step 2: Generate assistant response
        conv_id = conversation_id or uuid_mod.uuid4()
        response_text: str

        if self._chat_service is not None:
            try:
                chat_result = await self._chat_service.send_message(
                    user_id=user_id,
                    message=user_text,
                    conversation_id=conv_id,
                )
                # Accept either a dict with "content" or an object with .content
                if isinstance(chat_result, dict):
                    response_text = chat_result.get("content", str(chat_result))
                    conv_id = chat_result.get("conversation_id", conv_id)
                else:
                    response_text = getattr(chat_result, "content", str(chat_result))
                    conv_id = getattr(chat_result, "conversation_id", conv_id)
            except Exception as exc:
                logger.error("Chat service error during voice chat: %s", exc)
                response_text = (
                    "I apologize, but I encountered an error processing your request. "
                    "Please try again."
                )
        else:
            # No chat service -- echo mode
            response_text = (
                f"I heard you say: \"{user_text}\". "
                "The chat service is not connected, so I cannot provide a full response."
            )

        # Step 3: Synthesize response audio
        audio_url: Optional[str] = None
        try:
            audio_bytes = await self.synthesize(response_text)
            # In a production system this would be stored and served via a
            # URL.  For now we log the size; the API layer handles delivery.
            logger.debug(
                "Synthesized %d bytes of response audio", len(audio_bytes)
            )
            # The API router will attach the actual audio URL after storage.
        except Exception as exc:
            logger.warning("TTS failed during voice chat: %s", exc)

        return VoiceChatResponse(
            transcription=user_text,
            response_text=response_text,
            audio_url=audio_url,
            conversation_id=conv_id,
        )

    # ── Voice listing ────────────────────────────────────────────────────

    async def list_voices(self) -> list[VoiceInfo]:
        """
        List all available TTS voices from ElevenLabs.
        """
        try:
            raw_voices = await self._elevenlabs.list_voices()
        except Exception as exc:
            logger.warning("Failed to list ElevenLabs voices: %s", exc)
            return []

        voices: list[VoiceInfo] = []
        for v in raw_voices:
            voices.append(
                VoiceInfo(
                    voice_id=v.get("voice_id", ""),
                    name=v.get("name", "Unknown"),
                    category=v.get("category"),
                    labels=v.get("labels", {}),
                    preview_url=v.get("preview_url"),
                )
            )
        return voices

    # ── Voice cloning ────────────────────────────────────────────────────

    async def clone_voice(
        self,
        name: str,
        audio_files: list[bytes],
    ) -> dict[str, Any]:
        """
        Clone a voice from audio samples using the ElevenLabs API.

        This is a convenience wrapper that documents the cloning flow.
        Full voice cloning requires an ElevenLabs Professional or Creator
        plan.

        Parameters
        ----------
        name:
            Name for the new cloned voice.
        audio_files:
            List of audio sample byte arrays (WAV or MP3, 1--25 files,
            each at least 1 minute of clear speech recommended).

        Returns
        -------
        dict
            Voice metadata from ElevenLabs including the new ``voice_id``.
        """
        import httpx

        if not audio_files:
            raise ValueError("At least one audio file is required for voice cloning.")

        # Build multipart form data
        files = []
        for idx, audio in enumerate(audio_files):
            files.append(
                ("files", (f"sample_{idx}.wav", audio, "audio/wav"))
            )

        async with httpx.AsyncClient(
            base_url="https://api.elevenlabs.io/v1",
            headers={"xi-api-key": self._elevenlabs._api_key},
            timeout=httpx.Timeout(120.0),
        ) as client:
            response = await client.post(
                "/voices/add",
                data={"name": name, "description": f"Cloned voice: {name}"},
                files=files,
            )
            response.raise_for_status()
            return response.json()
