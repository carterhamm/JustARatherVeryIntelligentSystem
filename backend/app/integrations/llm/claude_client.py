"""Anthropic Claude LLM client.

Handles the Anthropic API's unique system message format: the ``system``
parameter is a top-level kwarg, not a message with role ``"system"``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

from anthropic import AsyncAnthropic, APIConnectionError, APITimeoutError, RateLimitError

from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.claude")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class ClaudeClient(BaseLLMClient):
    """Async wrapper around the Anthropic Messages API."""

    provider = LLMProvider.CLAUDE

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._client = AsyncAnthropic(
            api_key=api_key,
            max_retries=max_retries,
            timeout=60.0,
        )
        self.default_model = default_model
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        system_text, user_messages = self._extract_system(messages)

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_text:
            kwargs["system"] = system_text

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.messages.create(**kwargs)
                content = ""
                for block in response.content:
                    if block.type == "text":
                        content += block.text

                return {
                    "content": content,
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.input_tokens,
                        "completion_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                    },
                    "finish_reason": response.stop_reason,
                    "tool_calls": None,
                }
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Claude request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Claude request failed after {self._max_retries} retries"
        ) from last_exc

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        system_text, user_messages = self._extract_system(messages)

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_text:
            kwargs["system"] = system_text

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                async with self._client.messages.stream(**kwargs) as stream:
                    async for text in stream.text_stream:
                        yield text
                return
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Claude stream failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Claude stream failed after {self._max_retries} retries"
        ) from last_exc

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        # Anthropic uses ~4 chars per token as a rough estimate.
        # The official tokenizer is not publicly available as a library.
        return max(1, len(text) // 4)

    def get_cheap_model(self) -> str:
        return "claude-haiku-4-5-20251001"

    @staticmethod
    def _extract_system(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """Separate system messages from user/assistant messages.

        Anthropic expects ``system=`` as a top-level param, not as a
        message with ``role: "system"``.  This method concatenates all
        system messages and returns (system_text, remaining_messages).
        """
        system_parts: list[str] = []
        remaining: list[dict[str, str]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                if content.strip():
                    system_parts.append(content.strip())
            else:
                remaining.append({"role": role, "content": content})

        return "\n\n".join(system_parts), remaining
