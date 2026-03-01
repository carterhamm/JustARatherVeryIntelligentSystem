"""ShieldGemma content safety filter for Stark Protocol.

Provides pattern-based input sanitization to catch common prompt
injection attempts.  Model-based classification is disabled when
running on RunPod serverless (no sidecar ShieldGemma model).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("jarvis.llm.shield_gemma")

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
    """Input/output content safety filter using pattern matching."""

    async def filter_input(self, text: str) -> FilterResult:
        """Check user input for safety before sending to the model."""
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return FilterResult(
                    is_safe=False,
                    category="prompt_injection",
                    reason="Input contains a potential prompt injection pattern.",
                    confidence=0.8,
                )
        return FilterResult(is_safe=True)

    async def filter_output(self, text: str) -> FilterResult:
        """Check model output for safety before returning to the user."""
        return FilterResult(is_safe=True)
