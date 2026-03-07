"""Base LLM client and provider enum for the multi-model architecture."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Optional


class LLMProvider(str, enum.Enum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    STARK_PROTOCOL = "stark_protocol"


class BaseLLMClient(ABC):
    """Abstract base class for all LLM provider clients.

    Every provider must implement:
    * ``chat_completion`` — non-streaming request returning a dict.
    * ``chat_completion_stream`` — streaming request yielding content deltas.
    * ``count_tokens`` — approximate token count for a text string.
    """

    provider: LLMProvider
    default_model: str

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """Send a non-streaming chat completion and return the full response.

        Returns a dict with keys: ``content``, ``model``, ``usage``,
        ``finish_reason``, and optionally ``tool_calls``.
        """
        ...

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield incremental content-delta strings from a streaming request."""
        ...
        # Make this a proper async generator
        yield ""  # pragma: no cover

    @abstractmethod
    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        """Return the approximate token count for *text*."""
        ...

    def get_default_model(self) -> str:
        """Return the provider's default model identifier."""
        return self.default_model

    def get_cheap_model(self) -> str:
        """Return a cheap/fast model for auxiliary tasks like title generation."""
        return self.default_model
