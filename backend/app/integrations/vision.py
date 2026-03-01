"""
Async Vision client wrapping GPT-4o's multimodal capabilities.

Provides image analysis, OCR, and object detection by sending base64-encoded
images to the OpenAI chat completions API with vision-capable models.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)

logger = logging.getLogger("jarvis.vision")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


@dataclass
class VisionAnalysis:
    """Structured result from a GPT-4o vision analysis."""

    description: str
    objects: list[str] = field(default_factory=list)
    text_content: str = ""
    tags: list[str] = field(default_factory=list)
    raw_response: str = ""


class VisionClient:
    """
    Async client for GPT-4o vision analysis.

    All image data is base64-encoded and sent as inline ``image_url`` content
    parts in a chat completion request, so no external image hosting is
    required.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            max_retries=max_retries,
            timeout=120.0,
        )
        self._model = model
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    # ── Public API ───────────────────────────────────────────────────────

    async def analyze_image(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        detail: str = "auto",
    ) -> VisionAnalysis:
        """
        Analyze an image and return a structured :class:`VisionAnalysis`.

        Parameters
        ----------
        image_data:
            Raw image bytes (PNG, JPEG, GIF, or WebP).
        prompt:
            Optional custom prompt; merged with the default analysis prompt.
        detail:
            Image detail level: ``"low"``, ``"high"``, or ``"auto"``.
        """
        b64 = self._encode_image(image_data)
        system_prompt = self._build_vision_prompt("analyze", prompt)

        content = await self._vision_request(b64, system_prompt, detail)
        return self._parse_analysis(content)

    async def analyze_image_url(
        self,
        url: str,
        prompt: Optional[str] = None,
        detail: str = "auto",
    ) -> VisionAnalysis:
        """
        Analyze an image referenced by URL.

        The URL must be publicly accessible. For private images, use
        :meth:`analyze_image` with raw bytes instead.
        """
        system_prompt = self._build_vision_prompt("analyze", prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": url, "detail": detail},
                    },
                    {
                        "type": "text",
                        "text": "Analyze this image.",
                    },
                ],
            },
        ]

        content = await self._chat_request(messages)
        return self._parse_analysis(content)

    async def ocr(self, image_data: bytes) -> str:
        """
        Extract all visible text from an image using GPT-4o.

        Returns the recognized text as a single string.
        """
        b64 = self._encode_image(image_data)
        system_prompt = self._build_vision_prompt("ocr")

        return await self._vision_request(b64, system_prompt, detail="high")

    async def detect_objects(self, image_data: bytes) -> list[dict[str, Any]]:
        """
        Detect and describe objects visible in the image.

        Returns a list of dicts, each with ``name``, ``description``, and
        ``confidence`` keys.
        """
        import json as json_mod

        b64 = self._encode_image(image_data)
        system_prompt = self._build_vision_prompt("detect_objects")

        raw = await self._vision_request(b64, system_prompt, detail="auto")

        # GPT-4o is instructed to respond with JSON; parse it robustly.
        try:
            # Strip markdown fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Drop first and last fence lines
                cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
            parsed = json_mod.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and "objects" in parsed:
                return parsed["objects"]
            return [parsed]
        except (json_mod.JSONDecodeError, TypeError):
            # Return a single-item list with the raw text as a description
            logger.warning("Could not parse object detection JSON: %s", raw[:200])
            return [{"name": "unknown", "description": raw, "confidence": "low"}]

    # ── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _encode_image(image_data: bytes) -> str:
        """Base64-encode raw image bytes."""
        return base64.b64encode(image_data).decode("utf-8")

    @staticmethod
    def _build_vision_prompt(task: str, custom_prompt: Optional[str] = None) -> str:
        """
        Build the system prompt for a given vision task.

        Parameters
        ----------
        task:
            One of ``"analyze"``, ``"ocr"``, or ``"detect_objects"``.
        custom_prompt:
            Optional user-provided prompt appended to the system instructions.
        """
        base_prompts: dict[str, str] = {
            "analyze": (
                "You are JARVIS, an advanced AI vision system. Analyze the provided "
                "image thoroughly. Respond with a JSON object containing exactly these "
                "keys:\n"
                '- "description": a detailed natural-language description of the image\n'
                '- "objects": a JSON array of strings naming every distinct object visible\n'
                '- "text_content": any text visible in the image (empty string if none)\n'
                '- "tags": a JSON array of keyword tags summarizing the image\n'
                "Respond ONLY with valid JSON, no markdown fences."
            ),
            "ocr": (
                "You are JARVIS, an advanced AI vision system performing OCR. "
                "Extract ALL visible text from the image exactly as it appears, "
                "preserving line breaks and formatting where possible. "
                "Output ONLY the extracted text, nothing else. "
                "If no text is visible, respond with an empty string."
            ),
            "detect_objects": (
                "You are JARVIS, an advanced AI vision system performing object "
                "detection. Identify every distinct object in the image. "
                "Respond with a JSON array where each element is an object with keys:\n"
                '- "name": short object label\n'
                '- "description": brief description of the object and its context\n'
                '- "confidence": "high", "medium", or "low"\n'
                "Respond ONLY with valid JSON, no markdown fences."
            ),
        }

        prompt = base_prompts.get(task, base_prompts["analyze"])
        if custom_prompt:
            prompt += f"\n\nAdditional instructions: {custom_prompt}"
        return prompt

    async def _vision_request(
        self,
        base64_image: str,
        system_prompt: str,
        detail: str = "auto",
    ) -> str:
        """
        Send a vision request with an inline base64 image.

        Returns the raw text content of the assistant's response.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": detail,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Process this image according to your instructions.",
                    },
                ],
            },
        ]
        return await self._chat_request(messages)

    async def _chat_request(self, messages: list[dict[str, Any]]) -> str:
        """
        Execute a chat completion request with retries.
        """
        import asyncio

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=4096,
                    temperature=0.2,
                )
                return response.choices[0].message.content or ""
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2 ** attempt)
                logger.warning(
                    "Vision request failed (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    self._max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Vision request failed after {self._max_retries} retries"
        ) from last_exc

    def _parse_analysis(self, raw: str) -> VisionAnalysis:
        """
        Parse the raw GPT-4o response into a structured VisionAnalysis.

        The model is instructed to return JSON, but we handle cases where
        it wraps the response in markdown fences or returns plain text.
        """
        import json as json_mod

        cleaned = raw.strip()
        # Strip markdown code fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        try:
            data = json_mod.loads(cleaned)
            return VisionAnalysis(
                description=data.get("description", ""),
                objects=data.get("objects", []),
                text_content=data.get("text_content", ""),
                tags=data.get("tags", []),
                raw_response=raw,
            )
        except (json_mod.JSONDecodeError, TypeError):
            logger.warning("Could not parse vision analysis JSON; using raw text")
            return VisionAnalysis(
                description=raw,
                objects=[],
                text_content="",
                tags=[],
                raw_response=raw,
            )
