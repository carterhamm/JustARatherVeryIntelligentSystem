"""
Landmarks / saved-places API -- CRUD for user-pinned map locations.

Supports creating, listing, updating, and deleting landmarks, plus a
utility endpoint that parses Apple Maps URLs to extract coordinates.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_or_service, get_db
from app.models.landmark import Landmark
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Landmarks"])


# -- Schemas ----------------------------------------------------------------

class LandmarkCreate(BaseModel):
    name: str = Field(..., max_length=256)
    description: Optional[str] = Field(None)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = Field(None, max_length=512)
    apple_maps_url: Optional[str] = Field(None, max_length=1024)
    icon: Optional[str] = Field("pin", max_length=32)
    color: Optional[str] = Field("#f0a500", max_length=7)


class LandmarkUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=256)
    description: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    address: Optional[str] = Field(None, max_length=512)
    apple_maps_url: Optional[str] = Field(None, max_length=1024)
    icon: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, max_length=7)


class LandmarkResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    apple_maps_url: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    created_at: str
    updated_at: str


class ParseUrlRequest(BaseModel):
    url: str = Field(..., max_length=2048)


class ParseUrlResponse(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    parsed: bool = False


# -- Helpers ----------------------------------------------------------------

def _landmark_to_response(landmark: Landmark) -> LandmarkResponse:
    return LandmarkResponse(
        id=str(landmark.id),
        name=landmark.name,
        description=landmark.description,
        latitude=landmark.latitude,
        longitude=landmark.longitude,
        address=landmark.address,
        apple_maps_url=landmark.apple_maps_url,
        icon=landmark.icon,
        color=landmark.color,
        created_at=landmark.created_at.isoformat(),
        updated_at=landmark.updated_at.isoformat(),
    )


def _parse_apple_maps_url(url: str) -> dict:
    """Extract latitude, longitude, and address from an Apple Maps URL.

    Supported formats:
      - https://maps.apple.com/?ll=40.2969,-111.6946
      - https://maps.apple.com/?address=...&ll=40.2969,-111.6946
      - https://maps.apple.com/place?...&ll=40.2969,-111.6946
    """
    result: dict = {"latitude": None, "longitude": None, "address": None, "parsed": False}

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # Extract ll parameter
        ll_values = params.get("ll")
        if ll_values:
            ll = ll_values[0]
            parts = ll.split(",")
            if len(parts) == 2:
                result["latitude"] = float(parts[0].strip())
                result["longitude"] = float(parts[1].strip())
                result["parsed"] = True

        # Extract address parameter if present
        address_values = params.get("address")
        if address_values:
            result["address"] = address_values[0]

    except (ValueError, IndexError):
        pass

    return result


# -- Endpoints --------------------------------------------------------------

@router.post("", response_model=LandmarkResponse, status_code=status.HTTP_201_CREATED)
async def create_landmark(
    body: LandmarkCreate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Create a new saved place / landmark."""
    landmark = Landmark(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        latitude=body.latitude,
        longitude=body.longitude,
        address=body.address,
        apple_maps_url=body.apple_maps_url,
        icon=body.icon,
        color=body.color,
    )
    db.add(landmark)
    await db.commit()
    await db.refresh(landmark)

    logger.info("Landmark created: user=%s name=%s", current_user.id, landmark.name)
    return _landmark_to_response(landmark)


@router.get("", response_model=list[LandmarkResponse])
async def list_landmarks(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """List all landmarks for the current user, ordered by creation date."""
    result = await db.execute(
        select(Landmark)
        .where(Landmark.user_id == current_user.id)
        .order_by(Landmark.created_at.desc())
    )
    landmarks = result.scalars().all()
    return [_landmark_to_response(lm) for lm in landmarks]


@router.put("/{landmark_id}", response_model=LandmarkResponse)
async def update_landmark(
    landmark_id: uuid.UUID,
    body: LandmarkUpdate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing landmark (must own it)."""
    result = await db.execute(
        select(Landmark).where(
            Landmark.id == landmark_id,
            Landmark.user_id == current_user.id,
        )
    )
    landmark = result.scalar_one_or_none()
    if not landmark:
        raise HTTPException(status_code=404, detail="Landmark not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(landmark, field, value)

    await db.commit()
    await db.refresh(landmark)

    logger.info("Landmark updated: user=%s id=%s", current_user.id, landmark_id)
    return _landmark_to_response(landmark)


@router.delete("/{landmark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_landmark(
    landmark_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Delete a landmark (must own it)."""
    result = await db.execute(
        select(Landmark).where(
            Landmark.id == landmark_id,
            Landmark.user_id == current_user.id,
        )
    )
    landmark = result.scalar_one_or_none()
    if not landmark:
        raise HTTPException(status_code=404, detail="Landmark not found")

    await db.delete(landmark)
    await db.commit()

    logger.info("Landmark deleted: user=%s id=%s", current_user.id, landmark_id)
    return None


@router.post("/parse-url", response_model=ParseUrlResponse)
async def parse_apple_maps_url(body: ParseUrlRequest):
    """Parse an Apple Maps URL and extract coordinates + address.

    No auth required — this is a stateless utility endpoint.
    """
    result = _parse_apple_maps_url(body.url)
    return ParseUrlResponse(**result)
