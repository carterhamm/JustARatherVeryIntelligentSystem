"""
JARVIS Smart Home API router.

Provides REST endpoints for device discovery, state inspection, control,
and scene management via the Matter protocol bridge.

All endpoints require authentication via the ``get_current_active_user``
dependency.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_active_user
from app.integrations.matter import MatterClient
from app.models.user import User

logger = logging.getLogger("jarvis.api.smart_home")

router = APIRouter(prefix="/smart-home", tags=["smart-home"])


# ═════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ═════════════════════════════════════════════════════════════════════════════


class DeviceState(BaseModel):
    """Representation of a smart-home device."""

    device_id: str
    name: str
    device_type: str
    room: str = ""
    is_online: bool = True
    state: dict[str, Any] = Field(default_factory=dict)
    manufacturer: str = ""
    model: str = ""


class DeviceListResponse(BaseModel):
    """Response for listing discovered devices."""

    devices: list[DeviceState]
    total: int


class DeviceCommandRequest(BaseModel):
    """Request body for sending a command to a device."""

    command: str = Field(..., description="Command string, e.g. 'on', 'off', 'set_brightness'")
    params: dict[str, Any] = Field(default_factory=dict, description="Optional command parameters")


class DeviceCommandResponse(BaseModel):
    """Response after sending a device command."""

    success: bool
    device_id: str
    command: str
    message: str = ""


class SceneResponse(BaseModel):
    """Representation of a smart-home scene."""

    scene_id: str
    name: str
    description: str = ""
    devices: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = False


class SceneListResponse(BaseModel):
    """Response for listing scenes."""

    scenes: list[SceneResponse]
    total: int


class SceneActivateResponse(BaseModel):
    """Response after activating a scene."""

    success: bool
    scene_id: str
    message: str = ""


class DiscoverResponse(BaseModel):
    """Response after triggering device discovery."""

    devices: list[DeviceState]
    discovered: int


# ═════════════════════════════════════════════════════════════════════════════
# Dependency injection helpers
# ═════════════════════════════════════════════════════════════════════════════

_matter_client: Optional[MatterClient] = None


def get_matter_client() -> MatterClient:
    """Return (and lazily create) the singleton MatterClient."""
    global _matter_client
    if _matter_client is None:
        _matter_client = MatterClient()
    return _matter_client


# ═════════════════════════════════════════════════════════════════════════════
# REST endpoints
# ═════════════════════════════════════════════════════════════════════════════


@router.get(
    "/devices",
    response_model=DeviceListResponse,
    summary="List all discovered devices",
    description="Retrieve a list of all smart-home devices currently known to the Matter controller.",
)
async def list_devices(
    user: User = Depends(get_current_active_user),
    client: MatterClient = Depends(get_matter_client),
) -> DeviceListResponse:
    """List all discovered smart-home devices."""
    try:
        raw_devices = await client.discover_devices()
        devices = [DeviceState(**dev) for dev in raw_devices]
        return DeviceListResponse(devices=devices, total=len(devices))
    except Exception as exc:
        logger.error("Failed to list devices: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with smart-home controller: {exc}",
        )


@router.get(
    "/devices/{device_id}",
    response_model=DeviceState,
    summary="Get specific device state",
    description="Retrieve the current state and details of a specific smart-home device.",
)
async def get_device(
    device_id: str,
    user: User = Depends(get_current_active_user),
    client: MatterClient = Depends(get_matter_client),
) -> DeviceState:
    """Get the current state of a specific device."""
    try:
        raw_device = await client.get_device(device_id)
        return DeviceState(**raw_device)
    except Exception as exc:
        logger.error("Failed to get device %s: %s", device_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get device state: {exc}",
        )


@router.post(
    "/devices/{device_id}/command",
    response_model=DeviceCommandResponse,
    summary="Send command to device",
    description="Send a control command (e.g. 'on', 'off', 'set_brightness') to a specific device.",
)
async def send_device_command(
    device_id: str,
    request: DeviceCommandRequest,
    user: User = Depends(get_current_active_user),
    client: MatterClient = Depends(get_matter_client),
) -> DeviceCommandResponse:
    """Send a control command to a smart-home device."""
    try:
        success = await client.control_device(
            device_id=device_id,
            command=request.command,
            params=request.params if request.params else None,
        )
        return DeviceCommandResponse(
            success=success,
            device_id=device_id,
            command=request.command,
            message="Command executed successfully" if success else "Command was rejected by the device",
        )
    except Exception as exc:
        logger.error(
            "Failed to send command to device %s: %s", device_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send device command: {exc}",
        )


@router.get(
    "/scenes",
    response_model=SceneListResponse,
    summary="List all scenes",
    description="Retrieve all configured smart-home scenes.",
)
async def list_scenes(
    user: User = Depends(get_current_active_user),
    client: MatterClient = Depends(get_matter_client),
) -> SceneListResponse:
    """List all configured smart-home scenes."""
    try:
        raw_scenes = await client.list_scenes()
        scenes = [SceneResponse(**scene) for scene in raw_scenes]
        return SceneListResponse(scenes=scenes, total=len(scenes))
    except Exception as exc:
        logger.error("Failed to list scenes: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve scenes: {exc}",
        )


@router.post(
    "/scenes/{scene_id}/activate",
    response_model=SceneActivateResponse,
    summary="Activate a scene",
    description="Activate a scene, triggering all associated device commands.",
)
async def activate_scene(
    scene_id: str,
    user: User = Depends(get_current_active_user),
    client: MatterClient = Depends(get_matter_client),
) -> SceneActivateResponse:
    """Activate a smart-home scene."""
    try:
        success = await client.activate_scene(scene_id)
        return SceneActivateResponse(
            success=success,
            scene_id=scene_id,
            message="Scene activated successfully" if success else "Scene activation failed",
        )
    except Exception as exc:
        logger.error("Failed to activate scene %s: %s", scene_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to activate scene: {exc}",
        )


@router.post(
    "/discover",
    response_model=DiscoverResponse,
    summary="Trigger device discovery",
    description="Initiate a new Matter device discovery scan.",
)
async def discover_devices(
    user: User = Depends(get_current_active_user),
    client: MatterClient = Depends(get_matter_client),
) -> DiscoverResponse:
    """Trigger a fresh device discovery scan."""
    try:
        raw_devices = await client.discover_devices()
        devices = [DeviceState(**dev) for dev in raw_devices]
        logger.info(
            "Discovery triggered by user %s: found %d device(s)",
            user.id,
            len(devices),
        )
        return DiscoverResponse(devices=devices, discovered=len(devices))
    except Exception as exc:
        logger.error("Device discovery failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Device discovery failed: {exc}",
        )
