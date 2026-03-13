"""Camera API — live feed, PTZ control, gesture recognition, vision analysis."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.core.dependencies import get_current_active_user, get_user_from_token_or_query
from app.services.camera import CameraService

logger = logging.getLogger("jarvis.api.camera")
router = APIRouter(prefix="/camera", tags=["Camera"])


class PTZRequest(BaseModel):
    speed: float = 0.5
    duration: float = 0.5


# -- Status ----------------------------------------------------------------

@router.get("/status")
async def camera_status(user=Depends(get_current_active_user)) -> dict[str, Any]:
    """Get camera connection status and info."""
    try:
        return await CameraService.get_status()
    except Exception as exc:
        return {"online": False, "error": str(exc)}


# -- Snapshot --------------------------------------------------------------

@router.get("/snapshot")
async def camera_snapshot(user=Depends(get_current_active_user)):
    """Get a JPEG snapshot from the camera."""
    try:
        data = await CameraService.get_snapshot()
        return Response(content=data, media_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Camera unavailable: {exc}")


# -- MJPEG Stream ----------------------------------------------------------

@router.get("/stream")
async def camera_stream(user=Depends(get_user_from_token_or_query)):
    """Proxy MJPEG stream from the camera daemon.

    Accepts JWT via ``Authorization: Bearer`` header **or** ``?token=`` query
    param (required for ``<img>`` tags that cannot set HTTP headers).
    """
    try:
        return StreamingResponse(
            CameraService.stream_proxy(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stream unavailable: {exc}")


# -- PTZ Control -----------------------------------------------------------

@router.post("/ptz/{action}")
async def camera_ptz(
    action: str, body: PTZRequest = PTZRequest(), user=Depends(get_current_active_user)
) -> dict[str, Any]:
    """Send PTZ command: left, right, up, down, home, stop."""
    valid = {"left", "right", "up", "down", "home", "stop",
             "zoom_in", "zoom_out", "patrol"}
    if action not in valid:
        raise HTTPException(400, f"Invalid action. Use: {', '.join(sorted(valid))}")
    try:
        return await CameraService.ptz_command(action, body.speed, body.duration)
    except Exception as exc:
        raise HTTPException(502, f"PTZ command failed: {exc}")


# -- Gesture Recognition ---------------------------------------------------

@router.get("/gestures")
async def camera_gestures(user=Depends(get_current_active_user)) -> dict[str, Any]:
    """Get current gesture recognition state."""
    try:
        return await CameraService.get_gestures()
    except Exception as exc:
        return {"active": False, "gesture": None, "error": str(exc)}


# -- Vision Analysis -------------------------------------------------------

@router.post("/analyze")
async def camera_analyze(
    prompt: str = "", user=Depends(get_current_active_user)
) -> dict[str, str]:
    """Capture a frame and analyze it with Gemini vision."""
    result = await CameraService.analyze_frame(prompt)
    return {"analysis": result}
