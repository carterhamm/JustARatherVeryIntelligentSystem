"""MacBook Agent reporting endpoint.

Receives read-only data from the lightweight agent running on
Mr. Stark's MacBook: Focus mode changes, missed calls, unread messages.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import settings
from app.core.dependencies import get_current_active_user_or_service
from app.db.redis import get_redis_client
from app.models.user import User

logger = logging.getLogger("jarvis.api.macbook")

router = APIRouter(tags=["macbook"])

# TTL for cached reports (2 hours)
_REPORT_TTL = 7200


# ── Schemas ───────────────────────────────────────────────────────────


class MacBookReport(BaseModel):
    event: str
    data: dict[str, Any]


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/report")
async def macbook_report(
    body: MacBookReport,
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, str]:
    """Receive a report from the MacBook agent.

    Event types:
    - ``focus_change`` — Focus mode transition (sleep off = Carter woke up)
    - ``missed_calls`` — Missed FaceTime calls from the last hour
    - ``unread_messages`` — Unread iMessages count
    """
    redis = await get_redis_client()
    event = body.event
    data = body.data

    logger.info("MacBook agent report: event=%s", event)

    if event == "focus_change":
        # Store latest focus state
        await redis.cache_set(
            "jarvis:macbook:focus_state",
            json.dumps(data),
            ttl=_REPORT_TTL,
        )

        # If Sleep Focus just turned OFF, Carter woke up → morning greeting
        focus = data.get("focus", "")
        active = data.get("active", True)
        if focus == "sleep" and active is False:
            logger.info("Sleep Focus OFF — triggering morning greeting")
            try:
                await _trigger_morning_greeting()
            except Exception as exc:
                logger.exception("Morning greeting failed: %s", exc)

    elif event == "missed_calls":
        # Store missed calls for anticipatory.py to pick up
        calls = data.get("calls", [])
        await redis.cache_set(
            "jarvis:macbook:missed_calls",
            json.dumps(calls),
            ttl=_REPORT_TTL,
        )

    elif event == "unread_messages":
        # Store unread message data for anticipatory.py to pick up
        messages = data.get("messages", [])
        await redis.cache_set(
            "jarvis:macbook:unread_messages",
            json.dumps(messages),
            ttl=_REPORT_TTL,
        )

    else:
        logger.warning("Unknown MacBook agent event: %s", event)

    return {"status": "received"}


@router.get("/status")
async def macbook_status(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Return the latest MacBook agent data from Redis."""
    redis = await get_redis_client()

    focus_raw = await redis.cache_get("jarvis:macbook:focus_state")
    calls_raw = await redis.cache_get("jarvis:macbook:missed_calls")
    messages_raw = await redis.cache_get("jarvis:macbook:unread_messages")

    return {
        "focus_state": json.loads(focus_raw) if focus_raw else None,
        "missed_calls": json.loads(calls_raw) if calls_raw else None,
        "unread_messages": json.loads(messages_raw) if messages_raw else None,
    }


# ── Helpers ───────────────────────────────────────────────────────────


async def _trigger_morning_greeting() -> None:
    """Generate and deliver a personalized morning greeting.

    Delivery priority:
    1. Mac Mini iMCP bridge (play audio via Apple TV)
    2. Twilio phone call
    3. iMessage fallback
    """
    from app.integrations.llm.factory import get_llm_client

    # Generate a morning greeting via Gemini
    llm = get_llm_client("gemini")
    response = await llm.chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are JARVIS, Mr. Stark's AI assistant. "
                    "Generate a brief, warm morning greeting (2-3 sentences). "
                    "Be Paul Bettany's JARVIS — dry, British, efficient. "
                    "Mention that you noticed he just woke up."
                ),
            },
            {
                "role": "user",
                "content": "Carter just woke up (Sleep Focus turned off). Greet him.",
            },
        ],
        temperature=0.7,
        max_tokens=200,
    )
    greeting = response.get("content", "Good morning, sir.").strip()
    logger.info("Morning greeting generated: %s", greeting[:100])

    # Try iMCP bridge first (play TTS audio on Mac Mini → Apple TV)
    if settings.IMCP_BRIDGE_URL and settings.ELEVENLABS_API_KEY:
        try:
            from app.integrations.elevenlabs import ElevenLabsClient

            async with ElevenLabsClient(
                api_key=settings.ELEVENLABS_API_KEY,
                default_voice_id=settings.ELEVENLABS_VOICE_ID,
            ) as tts:
                audio_bytes = await tts.synthesize(greeting, output_format="mp3_44100_128")

            if audio_bytes:
                import base64

                audio_b64 = base64.b64encode(audio_bytes).decode()
                async with httpx.AsyncClient(timeout=30.0) as http:
                    resp = await http.post(
                        f"{settings.IMCP_BRIDGE_URL}/play-audio",
                        headers={"Authorization": f"Bearer {settings.IMCP_BRIDGE_KEY}"},
                        json={
                            "audio_b64": audio_b64,
                            "format": "mp3",
                            "target": "apple_tv",
                        },
                    )
                    if resp.status_code == 200:
                        logger.info("Morning greeting played via iMCP bridge")
                        return
                    logger.warning("iMCP playback returned %d", resp.status_code)
        except Exception as exc:
            logger.warning("iMCP morning greeting failed: %s", exc)

    # Fallback: Twilio phone call
    if settings.TWILIO_ACCOUNT_SID and settings.OWNER_PHONE:
        try:
            from app.integrations.twilio_client import call_user_with_audio
            from app.integrations.elevenlabs import ElevenLabsClient

            # Generate audio for the call
            if settings.ELEVENLABS_API_KEY:
                async with ElevenLabsClient(
                    api_key=settings.ELEVENLABS_API_KEY,
                    default_voice_id=settings.ELEVENLABS_VOICE_ID,
                ) as tts:
                    audio_bytes = await tts.synthesize(greeting, output_format="mp3_44100_128")

                if audio_bytes:
                    # Store audio in Redis for Twilio to fetch
                    redis = await get_redis_client()
                    import base64

                    audio_b64 = base64.b64encode(audio_bytes).decode()
                    audio_id = f"morning_greeting_{int(__import__('time').time())}"
                    await redis.cache_set(f"jarvis:audio:{audio_id}", audio_b64, ttl=600)

                    audio_url = f"https://app.malibupoint.dev/api/v1/voice/audio/{audio_id}"
                    sid = await call_user_with_audio(audio_url)
                    if sid:
                        logger.info("Morning greeting sent via Twilio call: %s", sid)
                        return
        except Exception as exc:
            logger.warning("Twilio morning greeting failed: %s", exc)

    # Final fallback: iMessage
    try:
        from app.integrations.mac_mini import send_imessage, is_configured

        if is_configured() and settings.OWNER_PHONE:
            await send_imessage(to=settings.OWNER_PHONE, text=greeting)
            logger.info("Morning greeting sent via iMessage")
            return
    except Exception as exc:
        logger.warning("iMessage morning greeting failed: %s", exc)

    logger.warning("All morning greeting delivery methods failed")
