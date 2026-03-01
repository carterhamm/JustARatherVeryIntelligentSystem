"""
JARVIS Vision API router.

Provides REST endpoints for image analysis, OCR, and object detection,
plus a WebSocket for real-time video frame analysis.

All endpoints require authentication via the ``get_current_user`` dependency
(assumed to be provided by the foundation auth module).
"""

from __future__ import annotations

import json
import logging
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

from app.integrations.vision import VisionClient
from app.schemas.vision import (
    ObjectDetectionResponse,
    OCRResponse,
    VisionAnalyzeResponse,
)
from app.core.dependencies import get_current_active_user
from app.core.security import decode_token
from app.models.user import User
from app.services.vision_service import VisionService

logger = logging.getLogger("jarvis.api.vision")

router = APIRouter(prefix="/vision", tags=["vision"])

# Maximum image upload size: 20 MB
_MAX_IMAGE_SIZE = 20 * 1024 * 1024

# Accepted image MIME types
_ACCEPTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
}

# ═════════════════════════════════════════════════════════════════════════════
# Dependency injection helpers
# ═════════════════════════════════════════════════════════════════════════════

_vision_service: Optional[VisionService] = None


def _get_settings() -> Any:
    """Import settings at call time to avoid circular imports."""
    try:
        from app.core.config import settings
        return settings
    except ImportError:
        import os

        class _Settings:
            OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

        return _Settings()


def get_vision_service() -> VisionService:
    """Return (and lazily create) the singleton VisionService."""
    global _vision_service
    if _vision_service is None:
        settings = _get_settings()
        client = VisionClient(api_key=settings.OPENAI_API_KEY)
        _vision_service = VisionService(vision_client=client)
    return _vision_service


# ═════════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═════════════════════════════════════════════════════════════════════════════


async def _read_and_validate_image(image: UploadFile) -> bytes:
    """
    Read an uploaded image file and validate its type and size.

    Raises :class:`HTTPException` on validation failure.
    """
    # Validate content type
    content_type = image.content_type or ""
    if content_type and content_type not in _ACCEPTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported image type '{content_type}'. "
                f"Accepted: {', '.join(sorted(_ACCEPTED_IMAGE_TYPES))}"
            ),
        )

    image_data = await image.read()
    if not image_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty image file",
        )

    if len(image_data) > _MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum size of {_MAX_IMAGE_SIZE // (1024 * 1024)} MB",
        )

    return image_data


# ═════════════════════════════════════════════════════════════════════════════
# REST endpoints
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/analyze",
    response_model=VisionAnalyzeResponse,
    summary="Analyze an image",
    description=(
        "Upload an image and receive a structured analysis including "
        "description, detected objects, visible text, and keyword tags."
    ),
)
async def analyze_image(
    image: UploadFile = File(..., description="Image file (PNG, JPEG, GIF, WebP)"),
    prompt: Optional[str] = Form(
        None, description="Custom prompt to guide the analysis"
    ),
    detail: str = Form(
        "auto",
        description="Image detail level: 'low', 'high', or 'auto'",
    ),
    user: User = Depends(get_current_active_user),
    svc: VisionService = Depends(get_vision_service),
) -> VisionAnalyzeResponse:
    """Analyze an uploaded image using GPT-4o vision."""
    if detail not in ("auto", "low", "high"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="detail must be 'auto', 'low', or 'high'",
        )

    image_data = await _read_and_validate_image(image)

    try:
        return await svc.analyze(
            image_data=image_data,
            prompt=prompt,
            detail=detail,
        )
    except Exception as exc:
        logger.error("Image analysis failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image analysis failed: {exc}",
        )


@router.post(
    "/ocr",
    response_model=OCRResponse,
    summary="Extract text from an image (OCR)",
    description="Upload an image and extract all visible text using GPT-4o.",
)
async def ocr_image(
    image: UploadFile = File(..., description="Image file containing text"),
    user: User = Depends(get_current_active_user),
    svc: VisionService = Depends(get_vision_service),
) -> OCRResponse:
    """Extract text from an uploaded image."""
    image_data = await _read_and_validate_image(image)

    try:
        return await svc.ocr(image_data)
    except Exception as exc:
        logger.error("OCR failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR failed: {exc}",
        )


@router.post(
    "/detect",
    response_model=ObjectDetectionResponse,
    summary="Detect objects in an image",
    description="Upload an image and detect/describe all visible objects.",
)
async def detect_objects(
    image: UploadFile = File(..., description="Image file for object detection"),
    user: User = Depends(get_current_active_user),
    svc: VisionService = Depends(get_vision_service),
) -> ObjectDetectionResponse:
    """Detect objects in an uploaded image."""
    image_data = await _read_and_validate_image(image)

    try:
        return await svc.detect_objects(image_data)
    except Exception as exc:
        logger.error("Object detection failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Object detection failed: {exc}",
        )


# ═════════════════════════════════════════════════════════════════════════════
# WebSocket for real-time video frame analysis
# ═════════════════════════════════════════════════════════════════════════════


@router.websocket("/ws/vision")
async def websocket_vision(
    websocket: WebSocket,
) -> None:
    """
    Real-time video frame analysis via WebSocket.

    Protocol
    --------
    1. Client connects with a ``token`` query parameter, **or** sends an
       initial JSON text frame with ``{"token": "<jwt>"}``.
    2. Client sends binary frames containing image data (individual
       video frames as PNG or JPEG).
    3. Server responds to each frame with a JSON text frame containing
       the analysis result.
    4. Either side can close the connection normally.

    Control messages (text frames):
    - ``{"type": "ping"}`` -- server replies with ``{"type": "pong"}``.
    - ``{"type": "close"}`` -- server closes gracefully.
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
    svc = get_vision_service()
    frame_count = 0

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                frame_data: bytes = message["bytes"]
                frame_count += 1

                if len(frame_data) > _MAX_IMAGE_SIZE:
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "detail": "Frame exceeds maximum size",
                            "frame": frame_count,
                        })
                    )
                    continue

                try:
                    analysis = await svc.analyze_frame(frame_data)
                    await websocket.send_text(
                        json.dumps({
                            "type": "analysis",
                            "frame": frame_count,
                            "description": analysis.get("description", ""),
                            "objects": analysis.get("objects", []),
                            "tags": analysis.get("tags", []),
                        })
                    )
                except Exception as exc:
                    logger.error(
                        "Frame %d analysis error: %s", frame_count, exc, exc_info=True
                    )
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "detail": f"Analysis error: {exc}",
                            "frame": frame_count,
                        })
                    )

            elif "text" in message and message["text"]:
                try:
                    control = json.loads(message["text"])
                    msg_type = control.get("type")

                    if msg_type == "ping":
                        await websocket.send_text(
                            json.dumps({"type": "pong"})
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
        logger.info(
            "Vision WebSocket disconnected for user %s (processed %d frames)",
            user_id,
            frame_count,
        )
    except Exception as exc:
        logger.error("Vision WebSocket error: %s", exc, exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
