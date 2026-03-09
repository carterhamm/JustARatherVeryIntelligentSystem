"""Cron-triggered endpoints for JARVIS autonomous routines.

Secured with SERVICE_API_KEY — only Railway cron or daemon processes
should call these endpoints.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import zoneinfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user_or_service, get_db
from app.db.redis import get_redis_client
from app.integrations.llm.factory import get_llm_client
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

logger = logging.getLogger("jarvis.cron")

router = APIRouter(prefix="/cron", tags=["Cron"])

_MTN = zoneinfo.ZoneInfo("America/Denver")


async def _get_owner(db: AsyncSession) -> User:
    """Get the single owner user."""
    result = await db.execute(
        select(User).where(User.is_active.is_(True)).limit(1)
    )
    owner = result.scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=500, detail="No active owner found")
    return owner


async def _gather_morning_data() -> dict[str, Any]:
    """Gather all data needed for the morning briefing."""
    from app.agents.tools import get_tool_registry

    registry = get_tool_registry()
    data: dict[str, Any] = {}

    now = datetime.now(tz=_MTN)
    data["date_time"] = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")

    # Weather
    weather_tool = registry.get("weather")
    if weather_tool:
        try:
            data["weather"] = await weather_tool.execute(
                {"location": "Orem, Utah", "type": "current"},
            )
        except Exception as exc:
            logger.warning("Morning weather failed: %s", exc)
            data["weather"] = "Weather unavailable."

    # Forecast
    if weather_tool:
        try:
            data["forecast"] = await weather_tool.execute(
                {"location": "Orem, Utah", "type": "forecast"},
            )
        except Exception as exc:
            data["forecast"] = ""

    # Calendar (via iMCP if available)
    cal_tool = registry.get("mac_events_fetch")
    if cal_tool:
        try:
            today = now.strftime("%Y-%m-%d")
            data["calendar"] = await cal_tool.execute(
                {"start_date": f"{today}T00:00:00", "end_date": f"{today}T23:59:59"},
            )
        except Exception as exc:
            logger.warning("Morning calendar failed: %s", exc)
            data["calendar"] = ""

    # News headlines
    news_tool = registry.get("news")
    if news_tool:
        try:
            data["news"] = await news_tool.execute(
                {"category": "technology", "limit": 3},
            )
        except Exception as exc:
            data["news"] = ""

    return data


_MORNING_PROMPT = """\
You are JARVIS composing a morning briefing for Mr. Stark. Write a spoken script (will be read aloud by TTS) that is:
- Natural, warm, British, Paul Bettany delivery
- 15-25 seconds when spoken (~40-70 words)
- Start with "Good morning, sir." then the time
- Include weather summary (temperature, conditions, what to wear if relevant)
- If there are calendar events, mention the first one or two briefly
- If there's interesting news, one sentence max
- End with something encouraging or a light Iron Man reference (vary it each day)
- Say "sir" lowercase, say "JARVIS" not "J.A.R.V.I.S."
- Do NOT use asterisks, markdown, or formatting — this is pure spoken text

Here is today's data:
{data}

Write ONLY the spoken script, nothing else."""


@router.post("/morning-routine")
async def morning_routine(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute the JARVIS morning routine.

    1. Gather weather, calendar, news
    2. Compose briefing script via Gemini
    3. Generate ElevenLabs audio
    4. Play on MacBook → AirPlay to Apple TV
    5. Start music
    """
    logger.info("Morning routine triggered")

    # 1. Gather data
    data = await _gather_morning_data()
    logger.info("Morning data gathered: %s", list(data.keys()))

    # 2. Generate briefing script via LLM
    llm = get_llm_client()
    prompt = _MORNING_PROMPT.format(data="\n".join(f"{k}: {v}" for k, v in data.items()))

    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": "You are JARVIS, writing a morning briefing script."},
            {"role": "user", "content": prompt},
        ],
    )
    script = response["content"].strip()
    logger.info("Morning script: %s", script[:200])

    # 3. Generate ElevenLabs audio
    from app.integrations.elevenlabs import ElevenLabsClient

    audio_bytes = None
    try:
        async with ElevenLabsClient(
            api_key=settings.ELEVENLABS_API_KEY,
            default_voice_id=settings.ELEVENLABS_VOICE_ID,
        ) as tts:
            audio_bytes = await tts.synthesize(script, output_format="mp3_44100_128")
        logger.info("Morning audio generated: %d bytes", len(audio_bytes))
    except Exception as exc:
        logger.exception("Morning TTS failed: %s", exc)

    # 4. Play on MacBook via iMCP bridge → AirPlay to Apple TV
    results = {"script": script, "audio_size": len(audio_bytes) if audio_bytes else 0}

    if audio_bytes and settings.IMCP_BRIDGE_URL:
        try:
            import httpx
            import base64

            audio_b64 = base64.b64encode(audio_bytes).decode()

            # Send audio to iMCP bridge for playback
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
                results["playback"] = resp.json() if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as exc:
            logger.warning("iMCP playback failed: %s", exc)
            results["playback"] = f"Failed: {exc}"

    # 5. Trigger music on MacBook → Apple TV
    if settings.IMCP_BRIDGE_URL:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.post(
                    f"{settings.IMCP_BRIDGE_URL}/run-shortcut",
                    headers={"Authorization": f"Bearer {settings.IMCP_BRIDGE_KEY}"},
                    json={
                        "shortcut_name": "JARVIS Morning Music",
                        "input": "Leave it in my Dreams by The Voidz",
                    },
                )
                results["music"] = resp.json() if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as exc:
            logger.warning("Music trigger failed: %s", exc)
            results["music"] = f"Failed: {exc}"

    # 6. Also store in chat history so JARVIS remembers the briefing
    try:
        owner = await _get_owner(db)
        redis = await get_redis_client()
        service = ChatService(db=db, redis=redis, llm_client=llm)
        chat_request = ChatRequest(
            message=f"[Morning Routine] I just woke up. Here's today's briefing you composed: {script}",
            model_provider="gemini",
            voice_enabled=False,
        )
        await service.chat(owner.id, chat_request)
    except Exception as exc:
        logger.warning("Failed to store morning briefing in chat: %s", exc)

    results["status"] = "ok"
    return results


@router.get("/morning-routine/config")
async def get_morning_config(
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, Any]:
    """Get current morning routine configuration."""
    r = await get_redis_client()
    wake_time = await r.cache_get("jarvis:morning:wake_time") or "06:45"
    music = await r.cache_get("jarvis:morning:music") or "Leave it in my Dreams by The Voidz"
    enabled = await r.cache_get("jarvis:morning:enabled") or "true"

    return {
        "wake_time": wake_time,
        "music": music,
        "enabled": enabled == "true",
    }


@router.post("/morning-routine/config")
async def set_morning_config(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_active_user_or_service),
) -> dict[str, str]:
    """Update morning routine configuration.

    JARVIS can call this when Mr. Stark says "wake me up at 7 tomorrow".
    """
    r = await get_redis_client()

    if "wake_time" in payload:
        await r.cache_set("jarvis:morning:wake_time", payload["wake_time"], ttl=86400 * 365)
    if "music" in payload:
        await r.cache_set("jarvis:morning:music", payload["music"], ttl=86400 * 365)
    if "enabled" in payload:
        await r.cache_set("jarvis:morning:enabled", str(payload["enabled"]).lower(), ttl=86400 * 365)

    return {"status": "updated"}
