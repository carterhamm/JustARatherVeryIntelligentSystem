"""
JARVIS Voice API router.

Provides REST endpoints for speech-to-text, text-to-speech, full voice-chat,
and a WebSocket for real-time bidirectional voice streaming.

All endpoints require authentication via the ``get_current_user`` dependency
(assumed to be provided by the foundation auth module).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse

from app.integrations.elevenlabs import ElevenLabsClient
from app.integrations.tts_fallback import CoquiTTSClient
from app.integrations.whisper import WhisperClient
from app.schemas.voice import (
    SynthesizeRequest,
    TranscribeResponse,
    VoiceChatResponse,
    VoiceListResponse,
)
from app.core.dependencies import get_current_active_user
from app.core.security import decode_token
from app.models.user import User
from app.services.voice_service import VoiceService

logger = logging.getLogger("jarvis.api.voice")

router = APIRouter(prefix="/voice", tags=["voice"])

# ═════════════════════════════════════════════════════════════════════════════
# Dependency injection helpers
# ═════════════════════════════════════════════════════════════════════════════

# These lazy singletons are initialised on first use via the settings
# provided by the foundation layer.  The functions are kept simple so
# they can be overridden in tests with ``app.dependency_overrides``.

_voice_service: Optional[VoiceService] = None


def _get_settings() -> Any:
    """Import settings at call time to avoid circular imports."""
    try:
        from app.core.config import settings
        return settings
    except ImportError:
        # Fallback for development / testing
        import os

        class _Settings:
            OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
            ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

        return _Settings()


_jarvis_tts = None


def _get_jarvis_tts():
    """Lazily create the JARVIS TTS client (remote or local)."""
    global _jarvis_tts
    if _jarvis_tts is None:
        from app.config import settings as app_settings
        if not app_settings.JARVIS_VOICE_ENABLED:
            return None
        from app.integrations.jarvis_tts import JarvisTTSClient
        if app_settings.JARVIS_VOICE_URL:
            _jarvis_tts = JarvisTTSClient(
                remote_url=app_settings.JARVIS_VOICE_URL,
                api_key=app_settings.JARVIS_VOICE_API_KEY,
            )
            logger.info("JARVIS TTS initialized (remote): %s", app_settings.JARVIS_VOICE_URL)
        elif app_settings.JARVIS_VOICE_SERVER:
            _jarvis_tts = JarvisTTSClient(
                voice_server_dir=app_settings.JARVIS_VOICE_SERVER,
            )
            logger.info("JARVIS TTS initialized (local): %s", app_settings.JARVIS_VOICE_SERVER)
    return _jarvis_tts


def get_voice_service() -> VoiceService:
    """Return (and lazily create) the singleton VoiceService."""
    global _voice_service
    if _voice_service is None:
        from app.config import settings as app_settings
        whisper = WhisperClient(api_key=app_settings.OPENAI_API_KEY)
        elevenlabs = ElevenLabsClient(api_key=app_settings.ELEVENLABS_API_KEY)
        fallback = CoquiTTSClient()

        _voice_service = VoiceService(
            whisper=whisper,
            elevenlabs=elevenlabs,
            chat_service=None,
            fallback_tts=fallback,
        )
    return _voice_service


# ═════════════════════════════════════════════════════════════════════════════
# REST endpoints
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribe audio to text",
    description=(
        "Upload an audio file and receive a structured transcription "
        "with timed segments."
    ),
)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio file (wav, mp3, m4a, webm)"),
    language: Optional[str] = Form(None, description="ISO-639-1 language hint"),
    user: User = Depends(get_current_active_user),
    svc: VoiceService = Depends(get_voice_service),
) -> TranscribeResponse:
    """Transcribe an uploaded audio file using Whisper."""
    if audio.content_type and not audio.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected audio file, got {audio.content_type}",
        )

    # Determine format from filename extension
    filename = audio.filename or "audio.wav"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    supported = {"wav", "mp3", "m4a", "webm", "ogg", "flac"}
    if ext not in supported:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio format '{ext}'. Supported: {', '.join(sorted(supported))}",
        )

    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file",
        )

    try:
        return await svc.transcribe(audio_data, language=language, format=ext)
    except Exception as exc:
        logger.error("Transcription failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {exc}",
        )


@router.post(
    "/synthesize",
    summary="Synthesize text to speech",
    description="Convert text to audio using ElevenLabs (or fallback TTS).",
    responses={
        200: {
            "content": {"audio/mpeg": {}},
            "description": "Audio data in the requested format.",
        }
    },
)
async def synthesize_speech(
    request: SynthesizeRequest,
    user: User = Depends(get_current_active_user),
    svc: VoiceService = Depends(get_voice_service),
) -> StreamingResponse:
    """Synthesize speech from text and return audio as a streaming response."""
    try:
        audio_bytes = await svc.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            model=request.model,
        )
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech synthesis failed: {exc}",
        )

    # Map output format to MIME type
    mime_map = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
    }
    content_type = mime_map.get(request.output_format, "audio/mpeg")

    return StreamingResponse(
        content=iter([audio_bytes]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="jarvis_speech.{request.output_format}"',
            "Content-Length": str(len(audio_bytes)),
        },
    )


@router.post(
    "/chat",
    response_model=VoiceChatResponse,
    summary="Full voice chat pipeline",
    description=(
        "Upload audio, receive transcription, AI response text, and "
        "synthesized audio URL in a single round-trip."
    ),
)
async def voice_chat(
    audio: UploadFile = File(..., description="Audio file from the user"),
    conversation_id: Optional[str] = Form(
        None, description="Existing conversation UUID to continue"
    ),
    model: Optional[str] = Form(None, description="Override LLM model"),
    user: User = Depends(get_current_active_user),
    svc: VoiceService = Depends(get_voice_service),
) -> VoiceChatResponse:
    """Execute the full voice chat pipeline: STT -> LLM -> TTS."""
    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file",
        )

    # Parse conversation ID
    conv_id: Optional[uuid.UUID] = None
    if conversation_id:
        try:
            conv_id = uuid.UUID(conversation_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid conversation_id format (expected UUID)",
            )

    # Determine format
    filename = audio.filename or "audio.wav"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"

    user_id = str(user.id)

    try:
        return await svc.voice_chat(
            user_id=str(user_id),
            audio_data=audio_data,
            conversation_id=conv_id,
            format=ext,
        )
    except Exception as exc:
        logger.error("Voice chat failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice chat failed: {exc}",
        )


@router.get(
    "/voices",
    response_model=VoiceListResponse,
    summary="List available voices",
    description="Retrieve the list of available TTS voices.",
)
async def list_voices(
    user: User = Depends(get_current_active_user),
    svc: VoiceService = Depends(get_voice_service),
) -> VoiceListResponse:
    """List all available TTS voices."""
    try:
        voices = await svc.list_voices()
        return VoiceListResponse(voices=voices)
    except Exception as exc:
        logger.error("Failed to list voices: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list voices: {exc}",
        )


# ═════════════════════════════════════════════════════════════════════════════
# WebSocket endpoint for real-time voice streaming
# ═════════════════════════════════════════════════════════════════════════════


@router.websocket("/ws/voice")
async def websocket_voice(
    websocket: WebSocket,
) -> None:
    """
    Real-time bidirectional voice WebSocket.

    Protocol
    --------
    1. Client connects with a ``token`` query parameter, **or** sends an
       initial JSON text frame with ``{"token": "<jwt>"}``.
    2. Client sends binary frames containing audio data.
    3. Server processes each audio chunk and responds with:
       - A JSON text frame: ``{"type": "transcription", "text": "..."}``
       - A binary frame with synthesized audio response.
       - A JSON text frame: ``{"type": "response", "text": "..."}``
    4. Either side can close the connection normally.
    """
    # --- Authentication ---
    token = websocket.query_params.get("token")

    if token:
        # Validate token from query params before accepting
        try:
            payload = decode_token(token)
            if payload.type != "access":
                await websocket.close(code=4001)
                return
            user_id = payload.sub
        except Exception:
            await websocket.close(code=4001)
            return
        await websocket.accept()
    else:
        # Fall back to auth via first message
        await websocket.accept()
        try:
            auth_message = await websocket.receive_text()
            auth_data = json.loads(auth_message)
            auth_token = auth_data.get("token")
            if not auth_token:
                await websocket.send_text(
                    json.dumps({"type": "error", "detail": "Missing auth token"})
                )
                await websocket.close(code=4001)
                return

            payload = decode_token(auth_token)
            if payload.type != "access":
                await websocket.send_text(
                    json.dumps({"type": "error", "detail": "Invalid token type"})
                )
                await websocket.close(code=4001)
                return
            user_id = payload.sub
        except WebSocketDisconnect:
            return
        except (json.JSONDecodeError, KeyError):
            await websocket.send_text(
                json.dumps({"type": "error", "detail": "Invalid auth handshake"})
            )
            await websocket.close(code=4001)
            return
        except Exception:
            await websocket.send_text(
                json.dumps({"type": "error", "detail": "Authentication failed"})
            )
            await websocket.close(code=4001)
            return

    await websocket.send_text(
        json.dumps({"type": "connected", "user_id": user_id})
    )

    # --- Main loop ---
    svc = get_voice_service()
    conversation_id: Optional[uuid.UUID] = None

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                audio_data: bytes = message["bytes"]

                try:
                    # Transcribe
                    transcription = await svc.transcribe(audio_data)
                    await websocket.send_text(
                        json.dumps({
                            "type": "transcription",
                            "text": transcription.text,
                            "language": transcription.language,
                            "duration": transcription.duration,
                        })
                    )

                    # Generate response via voice chat pipeline
                    result = await svc.voice_chat(
                        user_id=user_id,
                        audio_data=audio_data,
                        conversation_id=conversation_id,
                    )
                    conversation_id = result.conversation_id

                    # Send response text
                    await websocket.send_text(
                        json.dumps({
                            "type": "response",
                            "text": result.response_text,
                            "conversation_id": str(result.conversation_id),
                        })
                    )

                    # Synthesize and send audio response
                    try:
                        response_audio = await svc.synthesize(result.response_text)
                        await websocket.send_bytes(response_audio)
                    except Exception as tts_exc:
                        logger.warning("WS TTS failed: %s", tts_exc)
                        await websocket.send_text(
                            json.dumps({
                                "type": "tts_error",
                                "detail": str(tts_exc),
                            })
                        )

                except Exception as exc:
                    logger.error("WS voice processing error: %s", exc, exc_info=True)
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "detail": f"Processing error: {exc}",
                        })
                    )

            elif "text" in message and message["text"]:
                # Handle text control messages
                try:
                    control = json.loads(message["text"])
                    msg_type = control.get("type")

                    if msg_type == "ping":
                        await websocket.send_text(
                            json.dumps({"type": "pong"})
                        )
                    elif msg_type == "set_conversation":
                        cid = control.get("conversation_id")
                        conversation_id = uuid.UUID(cid) if cid else None
                        await websocket.send_text(
                            json.dumps({
                                "type": "conversation_set",
                                "conversation_id": str(conversation_id),
                            })
                        )
                    elif msg_type == "close":
                        break
                except json.JSONDecodeError:
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "detail": "Invalid JSON control message",
                        })
                    )

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected for user %s", user_id)
    except Exception as exc:
        logger.error("Voice WebSocket error: %s", exc, exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
