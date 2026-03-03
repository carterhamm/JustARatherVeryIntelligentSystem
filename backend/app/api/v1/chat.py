"""
Chat API router -- REST, SSE, and WebSocket endpoints for the JARVIS
chat system.

All endpoints require authentication.  The authenticated user is injected
via ``get_current_active_user`` (provided by the core.dependencies module).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_active_user, get_db
from app.core.security import decode_token
from app.db.redis import RedisClient, get_redis_client
from app.integrations.llm import BaseLLMClient, get_llm_client
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatStreamChunk,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
)
from app.services.chat_service import ChatService

logger = logging.getLogger("jarvis.api.chat")

router = APIRouter(tags=["Chat"])

# ═════════════════════════════════════════════════════════════════════════════
# Dependency helpers
# ═════════════════════════════════════════════════════════════════════════════


def _get_llm_client(provider: str | None = None) -> BaseLLMClient:
    """Build an LLM client for the given provider (or default)."""
    return get_llm_client(provider)


async def _get_redis() -> RedisClient:
    """Obtain the shared RedisClient singleton."""
    return await get_redis_client()


async def _build_chat_service(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(_get_redis),
) -> ChatService:
    """Assemble a :class:`ChatService` with all its dependencies."""
    llm_client = _get_llm_client()
    return ChatService(db=db, redis=redis, llm_client=llm_client)


async def _authenticate_ws_token(
    token: str,
    db: AsyncSession,
) -> User:
    """
    Validate a JWT token and resolve it to a :class:`User` ORM instance.
    Used exclusively for WebSocket authentication where the standard
    OAuth2 dependency cannot be applied.

    Raises ``ValueError`` if the token is invalid or the user cannot be
    found / is inactive.
    """
    payload = decode_token(token)  # raises HTTPException on invalid JWT
    if payload.type != "access":
        raise ValueError("Invalid token type")

    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()

    if user is None:
        raise ValueError("User not found")
    if not user.is_active:
        raise ValueError("Account is deactivated")

    return user


# ═════════════════════════════════════════════════════════════════════════════
# REST -- Conversation CRUD
# ═════════════════════════════════════════════════════════════════════════════


@router.get(
    "/providers",
    summary="List available LLM providers with status",
)
async def list_providers(
    current_user: User = Depends(get_current_active_user),
) -> list[dict]:
    """Return which providers are configured and available."""
    from app.integrations.llm.base import LLMProvider

    provider_info = []
    for p in LLMProvider:
        available = False
        reason = ""
        try:
            _get_llm_client(p)
            available = True
        except Exception as exc:
            reason = str(exc)
        provider_info.append({
            "id": p.value,
            "available": available,
            "reason": reason,
        })
    return provider_info


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> ConversationResponse:
    conversation = await service.create_conversation(current_user.id, data)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations for the authenticated user",
)
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> ConversationListResponse:
    conversations, total = await service.list_conversations(
        current_user.id, skip=skip, limit=limit
    )
    return ConversationListResponse(
        conversations=[
            ConversationResponse.model_validate(c) for c in conversations
        ],
        total=total,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get conversation details",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> ConversationResponse:
    try:
        conversation = await service.get_conversation(
            conversation_id, current_user.id
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to access this conversation",
        )
    return ConversationResponse.model_validate(conversation)


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update a conversation",
)
async def update_conversation(
    conversation_id: uuid.UUID,
    data: ConversationUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> ConversationResponse:
    try:
        conversation = await service.update_conversation(
            conversation_id, current_user.id, data
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to access this conversation",
        )
    return ConversationResponse.model_validate(conversation)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> None:
    try:
        await service.delete_conversation(conversation_id, current_user.id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to access this conversation",
        )


# ═════════════════════════════════════════════════════════════════════════════
# REST -- Messages
# ═════════════════════════════════════════════════════════════════════════════


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    summary="Get messages in a conversation (paginated)",
)
async def get_messages(
    conversation_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> list[MessageResponse]:
    try:
        messages = await service.get_messages(
            conversation_id, current_user.id, skip=skip, limit=limit
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to access this conversation",
        )
    return [MessageResponse.model_validate(m) for m in messages]


# ═════════════════════════════════════════════════════════════════════════════
# REST -- Non-streaming chat
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/chat",
    response_model=MessageResponse,
    summary="Send a message and receive a complete response",
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> MessageResponse:
    try:
        message = await service.chat(current_user.id, request)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to access this conversation",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM request failed: {exc}",
        )
    return MessageResponse.model_validate(message)


# ═════════════════════════════════════════════════════════════════════════════
# SSE -- Streaming chat via Server-Sent Events
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/chat/stream",
    summary="Stream a chat response via Server-Sent Events",
    response_class=StreamingResponse,
)
async def chat_stream_sse(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    service: ChatService = Depends(_build_chat_service),
) -> StreamingResponse:
    """
    Accept a :class:`ChatRequest` and return a ``text/event-stream``
    response whose ``data:`` lines contain JSON-serialised
    :class:`ChatStreamChunk` objects.
    """

    async def _event_generator():
        try:
            async for chunk in service.chat_stream(current_user.id, request):
                payload = chunk.model_dump_json()
                yield f"data: {payload}\n\n"
        except ValueError:
            error_chunk = ChatStreamChunk(
                type="error", error="Conversation not found"
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
        except PermissionError:
            error_chunk = ChatStreamChunk(
                type="error", error="Not authorised"
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"
        except Exception as exc:
            logger.exception("SSE stream error")
            error_chunk = ChatStreamChunk(
                type="error", error=str(exc)
            )
            yield f"data: {error_chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# WebSocket -- Streaming chat
# ═════════════════════════════════════════════════════════════════════════════


@router.websocket("/ws/chat")
async def chat_websocket(
    websocket: WebSocket,
    token: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket endpoint for real-time streaming chat.

    **Authentication** is performed via:
    1. A ``token`` query parameter on the connection URL, or
    2. The first JSON message sent over the socket, which must include
       a ``"token"`` field.

    Subsequent JSON messages must conform to the :class:`ChatRequest`
    schema.  The server streams back :class:`ChatStreamChunk` objects as
    JSON.
    """
    await websocket.accept()

    # ── Authenticate ─────────────────────────────────────────────────
    current_user: User | None = None

    if token:
        try:
            current_user = await _authenticate_ws_token(token, db)
        except Exception:
            await websocket.send_json(
                ChatStreamChunk(type="error", error="Invalid token").model_dump(
                    mode="json"
                )
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    if current_user is None:
        # Wait for authentication message
        try:
            auth_data = await websocket.receive_json()
            auth_token = auth_data.get("token")
            if not auth_token:
                await websocket.send_json(
                    ChatStreamChunk(
                        type="error", error="Token required"
                    ).model_dump(mode="json")
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            current_user = await _authenticate_ws_token(auth_token, db)
        except WebSocketDisconnect:
            return
        except Exception:
            await websocket.send_json(
                ChatStreamChunk(
                    type="error", error="Authentication failed"
                ).model_dump(mode="json")
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # ── Build service dependencies ───────────────────────────────────
    llm_client = _get_llm_client()
    redis = await _get_redis()
    service = ChatService(db=db, redis=redis, llm_client=llm_client)

    # Resolve user's preferred model provider for WebSocket messages
    user_preferences = current_user.preferences or {}
    ws_default_provider = user_preferences.get("model_preference")

    # ── Message loop ─────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_json()

            # Handle heartbeat ping/pong (not a chat message)
            msg_type = raw.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                request = ChatRequest(**raw)
                # Apply user's default provider if not specified in message
                if not request.model_provider and ws_default_provider:
                    request.model_provider = ws_default_provider
            except Exception as exc:
                await websocket.send_json(
                    ChatStreamChunk(
                        type="error",
                        error=f"Invalid request: {exc}",
                    ).model_dump(mode="json")
                )
                continue

            full_response_text = ""
            async for chunk in service.chat_stream(current_user.id, request):
                await websocket.send_json(chunk.model_dump(mode="json"))
                if chunk.type == "token" and chunk.content:
                    full_response_text += chunk.content

            # Synthesize voice if requested
            if request.voice_enabled and full_response_text.strip():
                try:
                    if request.model_provider == "stark_protocol":
                        # Use local JARVIS voice for Stark Protocol
                        from app.api.v1.voice import _get_jarvis_tts
                        jarvis_tts = _get_jarvis_tts()
                        if jarvis_tts:
                            audio_bytes = await jarvis_tts.synthesize(full_response_text)
                            await websocket.send_bytes(audio_bytes)
                        else:
                            logger.warning("JARVIS local TTS not available")
                    else:
                        # Use ElevenLabs for Uplink providers
                        from app.api.v1.voice import get_voice_service
                        voice_svc = get_voice_service()
                        audio_bytes = await voice_svc.synthesize(
                            text=full_response_text,
                            voice_id=settings.ELEVENLABS_VOICE_ID,
                        )
                        await websocket.send_bytes(audio_bytes)
                except Exception as tts_exc:
                    logger.warning("TTS synthesis failed: %s", tts_exc)

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected (user=%s)", current_user.id
        )
    except Exception:
        logger.exception("WebSocket error")
        try:
            await websocket.send_json(
                ChatStreamChunk(
                    type="error", error="Internal server error"
                ).model_dump(mode="json")
            )
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
