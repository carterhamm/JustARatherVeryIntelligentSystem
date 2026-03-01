"""Stark Protocol LLM client — self-hosted Gemma models via vLLM/Ollama.

Connects to an OpenAI-compatible API endpoint (vLLM or Ollama) and
includes a semantic router that directs simple queries to gemma-1b and
complex ones to gemma-27b.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Optional

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError

from app.integrations.llm.base import BaseLLMClient, LLMProvider
from app.integrations.llm.shield_gemma import ShieldGemmaFilter, FilterResult

logger = logging.getLogger("jarvis.llm.stark_protocol")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Models available on the Stark Protocol GPU server
_STARK_SMALL = "gemma-3-1b"
_STARK_LARGE = "gemma-3-27b"


class StarkProtocolRouter:
    """Decides between the small and large Gemma model.

    Routing heuristic:
    - Short messages (< 100 chars) with simple patterns -> small model
    - Everything else -> large model
    """

    _SIMPLE_PATTERNS = re.compile(
        r"^(hi|hello|hey|thanks|thank you|ok|yes|no|bye|good\s?(morning|night|evening|afternoon))"
        r"|^what\s+(time|day|date)\s+is\s+it"
        r"|^(convert|calculate)\s+\d",
        re.IGNORECASE,
    )

    @classmethod
    def route(cls, messages: list[dict[str, str]]) -> str:
        """Return the model name to use based on message complexity."""
        if not messages:
            return _STARK_LARGE

        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if not last_user_msg:
            return _STARK_LARGE

        # Short + simple pattern -> small model
        if len(last_user_msg) < 100 and cls._SIMPLE_PATTERNS.search(last_user_msg):
            return _STARK_SMALL

        # Long messages or complex patterns -> large model
        return _STARK_LARGE


class StarkProtocolClient(BaseLLMClient):
    """Client for the self-hosted Stark Protocol (Gemma) inference server."""

    provider = LLMProvider.STARK_PROTOCOL

    def __init__(
        self,
        base_url: str,
        default_model: str = _STARK_LARGE,
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key="not-needed",  # local server
            max_retries=max_retries,
            timeout=120.0,  # longer timeout for local inference
        )
        self.default_model = default_model
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._base_url = base_url
        self._shield = ShieldGemmaFilter(base_url)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        # Pre-filter input through ShieldGemma
        last_user_msg = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if last_user_msg:
            input_check = await self._shield.filter_input(last_user_msg)
            if not input_check.is_safe:
                return {
                    "content": (
                        f"I cannot process this request. Content flagged as "
                        f"potentially unsafe ({input_check.category}): {input_check.reason}"
                    ),
                    "model": "shieldgemma-2b",
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "finish_reason": "content_filter",
                    "tool_calls": None,
                }

        resolved_model = model or StarkProtocolRouter.route(messages)
        formatted = self._format_messages(messages)

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": formatted,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                return {
                    "content": choice.message.content or "",
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                    "finish_reason": choice.finish_reason,
                    "tool_calls": None,
                }
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Stark Protocol request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Stark Protocol request failed after {self._max_retries} retries"
        ) from last_exc

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        resolved_model = model or StarkProtocolRouter.route(messages)
        formatted = self._format_messages(messages)

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": formatted,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                stream = await self._client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content
                return
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Stark Protocol stream failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Stark Protocol stream failed after {self._max_retries} retries"
        ) from last_exc

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        # Gemma uses SentencePiece; ~4 chars per token is a reasonable estimate
        return max(1, len(text) // 4)

    async def health_check(self, retries: int = 3, delay: float = 5.0) -> bool:
        """Check if the Stark Protocol server is reachable.

        Supports retries with delay to handle cold starts.
        """
        for attempt in range(retries):
            try:
                models = await self._client.models.list()
                logger.info(
                    "Stark Protocol healthy: %d models available",
                    len(models.data),
                )
                return True
            except Exception as exc:
                logger.warning(
                    "Stark Protocol health check attempt %d/%d failed: %s",
                    attempt + 1, retries, exc,
                )
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        return False

    def get_cheap_model(self) -> str:
        return _STARK_SMALL

    @staticmethod
    def _format_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        formatted: list[dict[str, str]] = []
        for msg in messages:
            entry: dict[str, str] = {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            }
            if "name" in msg:
                entry["name"] = msg["name"]
            formatted.append(entry)
        return formatted
