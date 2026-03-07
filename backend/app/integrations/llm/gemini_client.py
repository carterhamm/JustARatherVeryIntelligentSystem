"""Google Gemini LLM client.

Uses the ``google-genai`` SDK.  Handles role mapping: the Gemini API
uses ``"model"`` where OpenAI uses ``"assistant"``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

from google import genai
from google.genai import types

from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.gemini")

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class GeminiClient(BaseLLMClient):
    """Async wrapper around the Google Gemini (genai) API."""

    provider = LLMProvider.GEMINI

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-3.1-flash-lite-preview",
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._api_key = api_key
        self._client = genai.Client(api_key=api_key)
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
        system_text, contents = self._prepare_messages(messages)
        model_name = model or self.default_model

        config = types.GenerateContentConfig(
            temperature=temperature,
        )
        if max_tokens is not None:
            config.max_output_tokens = max_tokens
        if system_text:
            config.system_instruction = system_text

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )

                content = response.text or ""
                usage = response.usage_metadata
                return {
                    "content": content,
                    "model": model_name,
                    "usage": {
                        "prompt_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                        "completion_tokens": getattr(usage, "candidates_token_count", 0) or 0,
                        "total_tokens": getattr(usage, "total_token_count", 0) or 0,
                    },
                    "finish_reason": "stop",
                    "tool_calls": None,
                }
            except Exception as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2**attempt)
                logger.warning(
                    "Gemini request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, self._max_retries, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Gemini request failed after {self._max_retries} retries"
        ) from last_exc

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        system_text, contents = self._prepare_messages(messages)
        model_name = model or self.default_model

        config = types.GenerateContentConfig(
            temperature=temperature,
        )
        if max_tokens is not None:
            config.max_output_tokens = max_tokens
        if system_text:
            config.system_instruction = system_text

        # Retry only the stream creation, not iteration (which would
        # duplicate already-yielded tokens).
        stream = await self._create_stream_with_retry(
            model_name, contents, config,
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def _create_stream_with_retry(
        self,
        model_name: str,
        contents: list,
        config: types.GenerateContentConfig,
    ):
        """Create a Gemini stream with retry on transient errors."""
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                # Fresh client each attempt — the genai.Client can hold
                # stale async connection state between calls.
                client = genai.Client(api_key=self._api_key)
                return await client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2 ** attempt)
                logger.warning(
                    "Gemini stream creation failed (attempt %d/%d): %s [%s] — retry in %.1fs",
                    attempt + 1, self._max_retries,
                    type(exc).__name__, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Gemini stream failed after {self._max_retries} retries: {last_exc}"
        ) from last_exc

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        # Gemini uses roughly 4 chars per token
        return max(1, len(text) // 4)

    def get_cheap_model(self) -> str:
        return "gemini-3.1-flash-lite-preview"

    @staticmethod
    def _prepare_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[types.Content]]:
        """Convert OpenAI-style messages to Gemini format.

        - Extracts system messages into a single string.
        - Maps ``"assistant"`` role to ``"model"`` (Gemini convention).
        """
        system_parts: list[str] = []
        contents: list[types.Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                if content.strip():
                    system_parts.append(content.strip())
                continue

            # Map assistant -> model for Gemini
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=content)],
                )
            )

        return "\n\n".join(system_parts), contents
