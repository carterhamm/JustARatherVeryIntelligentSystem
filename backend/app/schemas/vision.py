"""
Pydantic v2 schemas for the JARVIS vision system.

Covers image analysis, OCR, and object detection endpoints.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════════════
# Image analysis
# ═════════════════════════════════════════════════════════════════════════════


class VisionAnalyzeRequest(BaseModel):
    """
    Describes the companion fields for the image-analysis endpoint.

    The actual image file is received as ``UploadFile`` via multipart
    form-data; this schema documents the optional JSON fields.
    """

    prompt: Optional[str] = Field(
        None,
        max_length=2000,
        description="Custom prompt to guide the analysis.",
    )
    detail: str = Field(
        "auto",
        pattern=r"^(auto|low|high)$",
        description="Image detail level: 'low', 'high', or 'auto'.",
    )


class DetectedObject(BaseModel):
    """A single detected object within an image."""

    name: str = Field(..., description="Short label for the object.")
    description: str = Field("", description="Brief description and context.")
    confidence: str = Field(
        "medium",
        description="Confidence level: 'high', 'medium', or 'low'.",
    )


class VisionAnalyzeResponse(BaseModel):
    """Full analysis result for an uploaded image."""

    model_config = ConfigDict(from_attributes=True)

    description: str = Field(
        ..., description="Natural-language description of the image."
    )
    objects: list[str] = Field(
        default_factory=list,
        description="Names of distinct objects detected in the image.",
    )
    text_content: str = Field(
        "",
        description="Any text visible in the image.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Keyword tags summarizing the image.",
    )
    model: str = Field(
        "gpt-4o",
        description="Vision model used for the analysis.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# OCR
# ═════════════════════════════════════════════════════════════════════════════


class OCRRequest(BaseModel):
    """
    Describes the companion fields for the OCR endpoint.

    The actual image file is received as ``UploadFile`` via multipart
    form-data.
    """

    language_hint: Optional[str] = Field(
        None,
        max_length=10,
        description="Optional language hint for OCR (e.g. 'en', 'ja').",
    )


class OCRResponse(BaseModel):
    """OCR extraction result."""

    model_config = ConfigDict(from_attributes=True)

    text: str = Field(..., description="Extracted text from the image.")
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0.0 to 1.0) when available.",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Object detection
# ═════════════════════════════════════════════════════════════════════════════


class ObjectDetectionResponse(BaseModel):
    """Object detection result."""

    model_config = ConfigDict(from_attributes=True)

    objects: list[DetectedObject] = Field(
        default_factory=list,
        description="Detected objects with labels and descriptions.",
    )
