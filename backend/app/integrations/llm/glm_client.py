"""ZhipuAI GLM LLM client — OpenAI-compatible API at BigModel.

Uses the OpenAI Python SDK with a custom base URL pointing to
``https://open.bigmodel.cn/api/paas/v4``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, BadRequestError, RateLimitError

from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.glm")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

_GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# Ordered list of models to try if the default fails with a "model not found" error
_FALLBACK_MODELS = ["glm-4-flash", "glm-4-air", "glm-4", "glm-4-plus"]


class GLMClient(BaseLLMClient):
    """Async wrapper around ZhipuAI GLM via OpenAI-compatible API."""

    provider = LLMProvider.GLM

    def __init__(
        self,
        api_key: str,
        default_model: str = "glm-4-flash",
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=_GLM_BASE_URL,
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
        target_model = model or self.default_model
        models_to_try = [target_model] + [
            m for m in _FALLBACK_MODELS if m != target_model
        ]

        for model_name in models_to_try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            last_exc: BaseException | None = None
            for attempt in range(self._max_retries):
                try:
                    response = await self._client.chat.completions.create(**kwargs)
                    # If we had to fall back, update the default for future calls
                    if model_name != target_model:
                        logger.info("GLM model '%s' works — updating default", model_name)
                        self.default_model = model_name
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
                except BadRequestError as exc:
                    if "1211" in str(exc):
                        logger.warning("GLM model '%s' not found, trying next fallback", model_name)
                        break  # Try next model
                    raise  # Other 400 errors should propagate
                except _RETRYABLE_ERRORS as exc:
                    last_exc = exc
                    delay = self._retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "GLM request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, self._max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
            else:
                if last_exc:
                    raise RuntimeError(
                        f"GLM request failed after {self._max_retries} retries"
                    ) from last_exc

        raise RuntimeError(
            f"No available GLM model found. Tried: {', '.join(models_to_try)}"
        )

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        target_model = model or self.default_model
        models_to_try = [target_model] + [
            m for m in _FALLBACK_MODELS if m != target_model
        ]

        for model_name in models_to_try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            last_exc: BaseException | None = None
            for attempt in range(self._max_retries):
                try:
                    stream = await self._client.chat.completions.create(**kwargs)
                    if model_name != target_model:
                        logger.info("GLM stream model '%s' works — updating default", model_name)
                        self.default_model = model_name
                    async for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if delta and delta.content:
                            yield delta.content
                    return
                except BadRequestError as exc:
                    if "1211" in str(exc):
                        logger.warning("GLM stream model '%s' not found, trying next", model_name)
                        break
                    raise
                except _RETRYABLE_ERRORS as exc:
                    last_exc = exc
                    delay = self._retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "GLM stream failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, self._max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
            else:
                if last_exc:
                    raise RuntimeError(
                        f"GLM stream failed after {self._max_retries} retries"
                    ) from last_exc

        raise RuntimeError(
            f"No available GLM model found. Tried: {', '.join(models_to_try)}"
        )

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        # Approximate: ~4 chars per token for mixed content
        return max(1, len(text) // 4)

    def get_cheap_model(self) -> str:
        return "glm-4-flash"
