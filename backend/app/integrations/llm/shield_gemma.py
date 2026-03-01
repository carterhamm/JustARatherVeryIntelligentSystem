"""ShieldGemma content safety filter for Stark Protocol.

Provides input sanitization and output validation using the ShieldGemma
model running alongside the main Gemma models on the GPU server.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger("jarvis.llm.shield_gemma")

_SHIELD_MODEL = "shieldgemma-2b"

# Pattern-based pre-filter for common prompt injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+(?!jarvis)", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|(?:im_start|system|endoftext)\|>", re.IGNORECASE),
]


@dataclass
class FilterResult:
    """Result of a ShieldGemma content filter check."""
    is_safe: bool = True
    category: str = ""
    reason: str = ""
    confidence: float = 1.0


class ShieldGemmaFilter:
    """Input/output content safety filter using ShieldGemma.

    Falls back to pattern-based filtering if the ShieldGemma model is
    unavailable on the Stark Protocol server.
    """

    def __init__(self, base_url: str) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key="not-needed",
            timeout=10.0,
        )
        self._available: bool | None = None

    async def check_availability(self) -> bool:
        """Check if ShieldGemma model is loaded on the server."""
        if self._available is not None:
            return self._available
        try:
            models = await self._client.models.list()
            model_ids = [m.id for m in models.data]
            self._available = _SHIELD_MODEL in model_ids
        except Exception:
            self._available = False
        return self._available

    async def filter_input(self, text: str) -> FilterResult:
        """Check user input for safety before sending to the model."""
        # Pattern-based pre-filter (always active)
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return FilterResult(
                    is_safe=False,
                    category="prompt_injection",
                    reason="Input contains a potential prompt injection pattern.",
                    confidence=0.8,
                )

        # ShieldGemma model filter (if available)
        if await self.check_availability():
            return await self._model_filter(text, "input")

        return FilterResult(is_safe=True)

    async def filter_output(self, text: str) -> FilterResult:
        """Check model output for safety before returning to the user."""
        if await self.check_availability():
            return await self._model_filter(text, "output")
        return FilterResult(is_safe=True)

    async def _model_filter(self, text: str, direction: str) -> FilterResult:
        """Run text through the ShieldGemma model for classification."""
        try:
            prompt = (
                f"Classify the following {direction} text as SAFE or UNSAFE. "
                f"If UNSAFE, specify the category (harmful, hateful, sexual, "
                f"dangerous, deceptive). Reply with only: SAFE or "
                f"UNSAFE:<category>:<brief reason>\n\n"
                f"Text: {text[:2000]}"
            )

            response = await self._client.chat.completions.create(
                model=_SHIELD_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.0,
            )

            result_text = (response.choices[0].message.content or "").strip()

            if result_text.upper().startswith("SAFE"):
                return FilterResult(is_safe=True)

            # Parse UNSAFE:category:reason
            parts = result_text.split(":", 2)
            category = parts[1].strip().lower() if len(parts) > 1 else "unknown"
            reason = parts[2].strip() if len(parts) > 2 else "Content flagged as unsafe."
            return FilterResult(
                is_safe=False,
                category=category,
                reason=reason,
                confidence=0.9,
            )

        except Exception as exc:
            logger.warning("ShieldGemma filter error: %s — allowing content", exc)
            return FilterResult(is_safe=True)
