"""OpenAI LLM client — extracted from the original monolithic llm_client.py."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

import tiktoken
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError

from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.openai")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class OpenAIClient(BaseLLMClient):
    """Async wrapper around OpenAI's chat completions API."""

    provider = LLMProvider.OPENAI

    def __init__(
        self,
        api_key: str,
        default_model: str = "gpt-4o",
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._client = AsyncOpenAI(
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
        formatted = self._format_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
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
                    "tool_calls": (
                        [tc.model_dump() for tc in choice.message.tool_calls]
                        if choice.message.tool_calls
                        else None
                    ),
                }
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "OpenAI request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"OpenAI request failed after {self._max_retries} retries"
        ) from last_exc

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        formatted = self._format_messages(messages)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
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
                    "OpenAI stream failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"OpenAI stream failed after {self._max_retries} retries"
        ) from last_exc

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        model_name = model or self.default_model
        try:
            encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))

    def get_cheap_model(self) -> str:
        return "gpt-4o-mini"

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
