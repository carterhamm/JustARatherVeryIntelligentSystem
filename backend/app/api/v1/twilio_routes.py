"""Twilio webhook endpoints for JARVIS phone calls.

All voice uses ElevenLabs TTS with the custom JARVIS voice.
Audio is cached in-memory with auto-cleanup after 5 minutes.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user_or_service, get_db
from app.db.redis import get_redis_client
from app.integrations.llm.factory import get_llm_client
from app.integrations.twilio_client import (
    build_play_greeting_twiml,
    build_play_response_twiml,
    call_user_with_audio,
)
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

logger = logging.getLogger("jarvis.api.twilio")

router = APIRouter(prefix="/twilio", tags=["Twilio"])

# ═══════════════════════════════════════════════════════════════════════════
# In-memory audio cache (UUID → (mp3_bytes, created_at))
# ═══════════════════════════════════════════════════════════════════════════

_audio_cache: dict[str, tuple[bytes, float]] = {}
_AUDIO_TTL = 300  # 5 minutes


def _cache_audio(audio_bytes: bytes) -> str:
    """Store audio in cache and return its UUID key."""
    _cleanup_expired()
    audio_id = uuid.uuid4().hex
    _audio_cache[audio_id] = (audio_bytes, time.time())
    return audio_id


def _cleanup_expired() -> None:
    """Remove expired audio from cache."""
    now = time.time()
    expired = [k for k, (_, ts) in _audio_cache.items() if now - ts > _AUDIO_TTL]
    for k in expired:
        del _audio_cache[k]


def _audio_url(audio_id: str) -> str:
    """Build the public URL for a cached audio clip."""
    base = "https://app.malibupoint.dev"
    return f"{base}/api/v1/twilio/audio/{audio_id}"


# ═══════════════════════════════════════════════════════════════════════════
# ElevenLabs TTS helper
# ═══════════════════════════════════════════════════════════════════════════

async def _generate_jarvis_tts(text: str) -> bytes:
    """Generate JARVIS voice audio via ElevenLabs.

    Uses the configured ELEVENLABS_VOICE_ID for the custom JARVIS voice.
    Returns MP3 bytes.
    """
    from app.integrations.elevenlabs import ElevenLabsClient

    async with ElevenLabsClient(
        api_key=settings.ELEVENLABS_API_KEY,
        default_voice_id=settings.ELEVENLABS_VOICE_ID,
    ) as client:
        return await client.synthesize(text, output_format="mp3_44100_128")


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/audio/{audio_id}")
async def serve_audio(audio_id: str) -> Response:
    """Serve cached TTS audio to Twilio.

    No auth — Twilio needs to fetch this during a call.
    Audio auto-expires after 5 minutes.
    """
    entry = _audio_cache.get(audio_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audio not found or expired")
    audio_bytes, _ = entry
    return Response(content=audio_bytes, media_type="audio/mpeg")


@router.post("/incoming")
async def incoming_call(request: Request) -> Response:
    """Handle incoming calls to JARVIS's phone number.

    Generates ElevenLabs greeting audio and returns TwiML with <Play>.
    """
    try:
        greeting = "Good day, Sir. J.A.R.V.I.S. at your service. How may I assist you?"
        audio = await _generate_jarvis_tts(greeting)
        audio_id = _cache_audio(audio)

        fallback_text = "I didn't catch that, Sir. Please try again."
        fallback_audio = await _generate_jarvis_tts(fallback_text)
        fallback_id = _cache_audio(fallback_audio)

        twiml = build_play_greeting_twiml(
            _audio_url(audio_id),
            fallback_audio_url=_audio_url(fallback_id),
        )
    except Exception as exc:
        logger.exception("ElevenLabs TTS failed for greeting: %s", exc)
        # Graceful fallback — use Twilio's built-in TTS if ElevenLabs is down
        from twilio.twiml.voice_response import VoiceResponse, Gather
        response = VoiceResponse()
        gather = Gather(
            input="speech",
            action="/api/v1/twilio/process-speech",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say(
            "Good day, Sir. J.A.R.V.I.S. at your service. How may I assist you?",
            voice="Polly.Matthew-Neural",
            language="en-US",
        )
        response.append(gather)
        response.redirect("/api/v1/twilio/incoming")
        twiml = str(response)

    return Response(content=twiml, media_type="application/xml")


@router.post("/process-speech")
async def process_speech(
    request: Request,
    SpeechResult: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process speech from the user's phone call.

    Twilio sends the transcribed speech here. We send it to JARVIS,
    get a response, generate ElevenLabs audio, and return TwiML with <Play>.
    """
    if not SpeechResult.strip():
        try:
            audio = await _generate_jarvis_tts(
                "I didn't catch that, Sir. Could you repeat that?"
            )
            audio_id = _cache_audio(audio)
            twiml = build_play_response_twiml(_audio_url(audio_id), listen_again=True)
        except Exception:
            from twilio.twiml.voice_response import VoiceResponse, Gather
            response = VoiceResponse()
            gather = Gather(
                input="speech",
                action="/api/v1/twilio/process-speech",
                method="POST",
                speech_timeout="auto",
                language="en-US",
            )
            gather.say("I didn't catch that, Sir.", voice="Polly.Matthew-Neural")
            response.append(gather)
            twiml = str(response)
        return Response(content=twiml, media_type="application/xml")

    logger.info("Phone speech input: %s", SpeechResult)

    try:
        redis = await get_redis_client()
        llm_client = get_llm_client()
        service = ChatService(db=db, redis=redis, llm_client=llm_client)

        # Get the owner user (single-owner system)
        result = await db.execute(
            select(User).where(User.is_active.is_(True)).limit(1)
        )
        owner = result.scalar_one_or_none()
        if not owner:
            audio = await _generate_jarvis_tts(
                "I'm having trouble authenticating, Sir."
            )
            audio_id = _cache_audio(audio)
            twiml = build_play_response_twiml(_audio_url(audio_id), listen_again=False)
            return Response(content=twiml, media_type="application/xml")

        chat_request = ChatRequest(
            message=SpeechResult,
            model_provider="gemini",
            voice_enabled=False,
        )
        message = await service.chat(owner.id, chat_request)
        response_text = message.content

        # Generate JARVIS voice for the response
        audio = await _generate_jarvis_tts(response_text)
        audio_id = _cache_audio(audio)

        listen_again = "?" in response_text
        twiml = build_play_response_twiml(_audio_url(audio_id), listen_again=listen_again)
        return Response(content=twiml, media_type="application/xml")

    except Exception as exc:
        logger.exception("Failed to process phone speech: %s", exc)
        try:
            audio = await _generate_jarvis_tts(
                "I'm experiencing a momentary difficulty, Sir. Please try again."
            )
            audio_id = _cache_audio(audio)
            twiml = build_play_response_twiml(_audio_url(audio_id), listen_again=True)
        except Exception:
            from twilio.twiml.voice_response import VoiceResponse, Gather
            response = VoiceResponse()
            gather = Gather(
                input="speech",
                action="/api/v1/twilio/process-speech",
                method="POST",
                speech_timeout="auto",
                language="en-US",
            )
            gather.say(
                "I'm experiencing a momentary difficulty, Sir.",
                voice="Polly.Matthew-Neural",
            )
            response.append(gather)
            twiml = str(response)
        return Response(content=twiml, media_type="application/xml")


@router.post("/call-user")
async def trigger_call_user(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, str]:
    """Trigger JARVIS to call the user with a message.

    Generates ElevenLabs audio and places the call with <Play>.
    Requires auth (JWT or service key).
    """
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        audio = await _generate_jarvis_tts(message)
        audio_id = _cache_audio(audio)
        sid = await call_user_with_audio(_audio_url(audio_id))
    except Exception as exc:
        logger.exception("Failed to generate audio for outbound call: %s", exc)
        raise HTTPException(status_code=503, detail=f"TTS failed: {exc}")

    if not sid:
        raise HTTPException(
            status_code=503, detail="Twilio not configured or call failed"
        )

    return {"status": "ok", "call_sid": sid}
