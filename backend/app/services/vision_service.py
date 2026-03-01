"""
JARVIS Vision Service.

Orchestrates image analysis, OCR, and object detection through the
GPT-4o vision integration client.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.integrations.vision import VisionClient
from app.schemas.vision import (
    DetectedObject,
    ObjectDetectionResponse,
    OCRResponse,
    VisionAnalyzeResponse,
)

logger = logging.getLogger("jarvis.vision_service")


class VisionService:
    """
    High-level vision service that wraps :class:`VisionClient` and maps
    raw analysis results into Pydantic response schemas.

    Parameters
    ----------
    vision_client:
        The underlying GPT-4o vision integration client.
    """

    def __init__(self, vision_client: VisionClient) -> None:
        self._client = vision_client

    # ── Image analysis ───────────────────────────────────────────────────

    async def analyze(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        detail: str = "auto",
    ) -> VisionAnalyzeResponse:
        """
        Perform a full analysis of an image.

        Parameters
        ----------
        image_data:
            Raw image bytes (PNG, JPEG, GIF, or WebP).
        prompt:
            Optional custom prompt to guide the analysis.
        detail:
            Image detail level: ``"low"``, ``"high"``, or ``"auto"``.

        Returns
        -------
        VisionAnalyzeResponse
            Structured analysis including description, detected objects,
            visible text, and keyword tags.
        """
        analysis = await self._client.analyze_image(
            image_data=image_data,
            prompt=prompt,
            detail=detail,
        )

        return VisionAnalyzeResponse(
            description=analysis.description,
            objects=analysis.objects,
            text_content=analysis.text_content,
            tags=analysis.tags,
            model="gpt-4o",
        )

    # ── OCR ──────────────────────────────────────────────────────────────

    async def ocr(self, image_data: bytes) -> OCRResponse:
        """
        Extract visible text from an image.

        Parameters
        ----------
        image_data:
            Raw image bytes.

        Returns
        -------
        OCRResponse
            Extracted text and an optional confidence estimate.
        """
        text = await self._client.ocr(image_data)

        # GPT-4o does not provide a native confidence score, so we use a
        # heuristic: non-empty text with reasonable length gets high
        # confidence; very short or empty text gets lower confidence.
        confidence: Optional[float] = None
        if text.strip():
            confidence = min(0.95, 0.7 + 0.01 * len(text.strip()))
        else:
            confidence = 0.0

        return OCRResponse(
            text=text.strip(),
            confidence=round(confidence, 2),
        )

    # ── Object detection ─────────────────────────────────────────────────

    async def detect_objects(self, image_data: bytes) -> ObjectDetectionResponse:
        """
        Detect and describe objects in an image.

        Parameters
        ----------
        image_data:
            Raw image bytes.

        Returns
        -------
        ObjectDetectionResponse
            List of detected objects with labels, descriptions, and
            confidence levels.
        """
        raw_objects = await self._client.detect_objects(image_data)

        detected = []
        for obj in raw_objects:
            detected.append(
                DetectedObject(
                    name=obj.get("name", "unknown"),
                    description=obj.get("description", ""),
                    confidence=obj.get("confidence", "medium"),
                )
            )

        return ObjectDetectionResponse(objects=detected)

    # ── Real-time frame analysis ─────────────────────────────────────────

    async def analyze_frame(
        self,
        frame_data: bytes,
    ) -> dict[str, Any]:
        """
        Perform a lightweight analysis of a single video frame.

        This is optimized for real-time / WebSocket usage where latency
        matters more than exhaustive detail.  Uses ``detail="low"`` to
        reduce token usage and response time.

        Parameters
        ----------
        frame_data:
            Raw image bytes for a single video frame.

        Returns
        -------
        dict
            Lightweight analysis result with ``description`` and ``objects``.
        """
        analysis = await self._client.analyze_image(
            image_data=frame_data,
            prompt=(
                "Briefly describe what you see in this video frame. "
                "Focus on the main subject and any notable activity. "
                "Keep your response concise (1-2 sentences)."
            ),
            detail="low",
        )

        return {
            "description": analysis.description,
            "objects": analysis.objects,
            "tags": analysis.tags,
        }
