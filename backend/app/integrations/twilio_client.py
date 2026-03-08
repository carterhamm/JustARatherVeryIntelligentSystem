"""Twilio integration — JARVIS phone number for voice calls.

Uses ElevenLabs TTS for the JARVIS voice instead of generic Polly/Google.
Audio is generated, cached, and served via <Play> URLs in TwiML.
"""

from __future__ import annotations

import logging
from typing import Optional

from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.config import settings

logger = logging.getLogger("jarvis.twilio")

_client: Optional[TwilioClient] = None


def get_twilio_client() -> Optional[TwilioClient]:
    """Return the Twilio client singleton, or None if not configured."""
    global _client
    if _client:
        return _client
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return None
    _client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


async def call_user_with_audio(audio_url: str) -> Optional[str]:
    """Make an outbound call that plays ElevenLabs audio.

    Returns the call SID or None on failure.
    """
    client = get_twilio_client()
    if not client or not settings.TWILIO_PHONE_NUMBER or not settings.TWILIO_USER_PHONE:
        logger.warning("Twilio not configured — cannot call user")
        return None

    twiml = VoiceResponse()
    twiml.play(audio_url)

    try:
        call = client.calls.create(
            to=settings.TWILIO_USER_PHONE,
            from_=settings.TWILIO_PHONE_NUMBER,
            twiml=str(twiml),
        )
        logger.info("Placed call to user: %s", call.sid)
        return call.sid
    except Exception as exc:
        logger.exception("Failed to call user: %s", exc)
        return None


async def call_user_with_url(webhook_url: str) -> Optional[str]:
    """Make an outbound call that uses a webhook URL for dynamic TwiML."""
    client = get_twilio_client()
    if not client or not settings.TWILIO_PHONE_NUMBER or not settings.TWILIO_USER_PHONE:
        return None

    try:
        call = client.calls.create(
            to=settings.TWILIO_USER_PHONE,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=webhook_url,
        )
        return call.sid
    except Exception as exc:
        logger.exception("Failed to call user: %s", exc)
        return None


def build_play_greeting_twiml(audio_url: str, fallback_audio_url: Optional[str] = None) -> str:
    """Build TwiML that plays JARVIS greeting and gathers speech.

    Uses <Play> with ElevenLabs audio instead of <Say> with Polly.
    """
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/api/v1/twilio/process-speech",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.play(audio_url)
    response.append(gather)
    # If no speech detected, redirect to try again
    if fallback_audio_url:
        response.play(fallback_audio_url)
    response.redirect("/api/v1/twilio/incoming")
    return str(response)


def build_play_response_twiml(audio_url: str, listen_again: bool = True) -> str:
    """Build TwiML that plays JARVIS's response and optionally listens again."""
    response = VoiceResponse()
    if listen_again:
        gather = Gather(
            input="speech",
            action="/api/v1/twilio/process-speech",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.play(audio_url)
        response.append(gather)
    else:
        response.play(audio_url)
    return str(response)
