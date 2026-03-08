"""Twilio webhook endpoints for JARVIS phone calls."""

from __future__ import annotations

import logging
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
    build_greeting_twiml,
    build_response_twiml,
    call_user,
)
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

logger = logging.getLogger("jarvis.api.twilio")

router = APIRouter(prefix="/twilio", tags=["Twilio"])


@router.post("/incoming")
async def incoming_call(request: Request) -> Response:
    """Handle incoming calls to JARVIS's phone number.

    Returns TwiML that greets the user and starts listening.
    Twilio sends webhooks here — no auth needed (Twilio validates itself).
    """
    twiml = build_greeting_twiml()
    return Response(content=twiml, media_type="application/xml")


@router.post("/process-speech")
async def process_speech(
    request: Request,
    SpeechResult: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Process speech from the user's phone call.

    Twilio sends the transcribed speech here. We send it to JARVIS,
    get a response, and return TwiML that speaks it back.
    """
    if not SpeechResult.strip():
        twiml = build_response_twiml(
            "I didn't catch that, Sir. Could you repeat that?",
            listen_again=True,
        )
        return Response(content=twiml, media_type="application/xml")

    logger.info("Phone speech input: %s", SpeechResult)

    # Send to JARVIS chat
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
            twiml = build_response_twiml(
                "I'm having trouble authenticating, Sir.",
                listen_again=False,
            )
            return Response(content=twiml, media_type="application/xml")

        chat_request = ChatRequest(
            message=SpeechResult,
            model_provider="gemini",
            voice_enabled=False,
        )
        message = await service.chat(owner.id, chat_request)
        response_text = message.content

        # Check if response asks a question (keep listening)
        listen_again = "?" in response_text
        twiml = build_response_twiml(response_text, listen_again=listen_again)
        return Response(content=twiml, media_type="application/xml")

    except Exception as exc:
        logger.exception("Failed to process phone speech: %s", exc)
        twiml = build_response_twiml(
            "I'm experiencing a momentary difficulty, Sir. Please try again.",
            listen_again=True,
        )
        return Response(content=twiml, media_type="application/xml")


@router.post("/call-user")
async def trigger_call_user(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, str]:
    """Trigger JARVIS to call the user with a message.

    Requires auth (JWT or service key). Used by cron jobs,
    morning routine, or JARVIS's autonomous processes.
    """
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    sid = await call_user(message)
    if not sid:
        raise HTTPException(
            status_code=503, detail="Twilio not configured or call failed"
        )

    return {"status": "ok", "call_sid": sid}
