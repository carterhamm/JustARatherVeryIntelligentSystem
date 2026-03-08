"""Twilio integration — JARVIS phone number for voice calls."""

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


async def call_user(message: str, voice: str = "Polly.Brian-Neural") -> Optional[str]:
    """Make an outbound call to the user and speak a message.

    Uses Amazon Polly Brian (British male) for the JARVIS voice on phone.
    Returns the call SID or None on failure.
    """
    client = get_twilio_client()
    if not client or not settings.TWILIO_PHONE_NUMBER or not settings.TWILIO_USER_PHONE:
        logger.warning("Twilio not configured — cannot call user")
        return None

    twiml = VoiceResponse()
    twiml.say(message, voice=voice, language="en-GB")

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
    """Make an outbound call that uses a webhook URL for dynamic TwiML.

    The webhook handles the full conversation flow (STT -> JARVIS -> TTS).
    """
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


def build_greeting_twiml() -> str:
    """Build TwiML for when the user calls JARVIS.

    Greets the user and gathers speech input.
    """
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
        voice="Polly.Brian-Neural",
        language="en-GB",
    )
    response.append(gather)
    # If no speech detected, prompt again
    response.say(
        "I didn't catch that, Sir. Please try again.",
        voice="Polly.Brian-Neural",
        language="en-GB",
    )
    response.redirect("/api/v1/twilio/incoming")
    return str(response)


def build_response_twiml(text: str, listen_again: bool = True) -> str:
    """Build TwiML that speaks JARVIS's response and optionally listens again."""
    response = VoiceResponse()
    if listen_again:
        gather = Gather(
            input="speech",
            action="/api/v1/twilio/process-speech",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say(text, voice="Polly.Brian-Neural", language="en-GB")
        response.append(gather)
    else:
        response.say(text, voice="Polly.Brian-Neural", language="en-GB")
    return str(response)
