"""Stark Protocol LLM client — local Gemma 3 via LM Studio (OpenAI-compatible).

Connects to a local LM Studio server running an OpenAI-compatible API.
Supports both streaming and non-streaming chat completions.
Handles reconnection on transient failures (e.g. Mac sleep/wake).
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Optional

import httpx

from app.integrations.llm.base import BaseLLMClient, LLMProvider
from app.integrations.llm.shield_gemma import ShieldGemmaFilter, FilterResult

logger = logging.getLogger("jarvis.llm.stark_protocol")

# Default model name — LM Studio serves whatever is loaded,
# but we pass the identifier for logging / routing purposes.
_DEFAULT_MODEL = "gemma-3-4b-it-abliterated-text"

# Retry config for transient errors (e.g. LM Studio not running yet)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class StarkProtocolClient(BaseLLMClient):
    """Client for local LLM inference via LM Studio's OpenAI-compatible API."""

    provider = LLMProvider.STARK_PROTOCOL
    default_model = _DEFAULT_MODEL

    def __init__(
        self,
        endpoint_url: str,
        api_key: str = "lm-studio",
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._endpoint_url = endpoint_url.rstrip("/")
        self._api_key = api_key
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            timeout=120.0,  # local inference can take a while
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        self._shield = ShieldGemmaFilter()

    # ------------------------------------------------------------------
    # OpenAI-compatible chat completion (non-streaming)
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        # Pre-filter input through ShieldGemma patterns
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
                    "model": model or _DEFAULT_MODEL,
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "finish_reason": "content_filter",
                    "tool_calls": None,
                }

        payload = {
            "model": model or _DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
            "stream": False,
        }

        start = time.monotonic()
        data = await self._request_with_retry(payload)
        latency = time.monotonic() - start

        # Parse standard OpenAI chat completion response
        choices = data.get("choices", [])
        if choices:
            choice = choices[0]
            content = choice.get("message", {}).get("content", "")
            finish_reason = choice.get("finish_reason", "stop")
        else:
            content = ""
            finish_reason = "stop"

        usage = data.get("usage", {})
        token_usage = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

        logger.info(
            "Stark Protocol response: %.1fs, %d chars, %d tokens",
            latency, len(content), token_usage.get("total_tokens", 0),
        )

        return {
            "content": content,
            "model": data.get("model", model or _DEFAULT_MODEL),
            "usage": token_usage,
            "finish_reason": finish_reason,
            "tool_calls": None,
        }

    # ------------------------------------------------------------------
    # Streaming chat completion (SSE)
    # ------------------------------------------------------------------

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": model or _DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
            "stream": True,
        }

        url = f"{self._endpoint_url}/chat/completions"

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                async with self._http.stream(
                    "POST", url, json=payload, timeout=180.0,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            return

                        import json
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                    return  # Stream completed successfully

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "LM Studio stream error (%s), attempt %d/%d — retry in %.1fs",
                    type(exc).__name__, attempt + 1, self._max_retries, delay,
                )
                import asyncio
                await asyncio.sleep(delay)

        # If all retries failed, fall back to non-streaming
        logger.warning("Streaming failed after %d retries, falling back to non-streaming", self._max_retries)
        result = await self.chat_completion(messages, model, temperature, max_tokens)
        content = result.get("content", "")
        chunk_size = 20
        for i in range(0, len(content), chunk_size):
            yield content[i : i + chunk_size]

    # ------------------------------------------------------------------
    # Token counting (approximate)
    # ------------------------------------------------------------------

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        # Approximate: ~4 chars per token for English
        return max(1, len(text) // 4)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self, retries: int = 2, delay: float = 2.0) -> bool:
        """Check if LM Studio is running and responsive."""
        import asyncio
        for attempt in range(retries):
            try:
                resp = await self._http.get(f"{self._endpoint_url}/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        model_ids = [m.get("id", "unknown") for m in models]
                        logger.info("LM Studio healthy, models: %s", model_ids)
                    else:
                        logger.info("LM Studio healthy, no models loaded")
                    return True
            except Exception as exc:
                logger.warning(
                    "LM Studio health check %d/%d failed: %s",
                    attempt + 1, retries, exc,
                )
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        return False

    def get_cheap_model(self) -> str:
        return _DEFAULT_MODEL

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request_with_retry(self, payload: dict) -> dict:
        """POST to /chat/completions with retry on transient errors."""
        import asyncio
        url = f"{self._endpoint_url}/chat/completions"
        last_exc: BaseException | None = None

        for attempt in range(self._max_retries):
            try:
                resp = await self._http.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "LM Studio request error (%s), attempt %d/%d — retry in %.1fs",
                    type(exc).__name__, attempt + 1, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as exc:
                # Non-transient HTTP error — don't retry
                raise RuntimeError(
                    f"LM Studio error {exc.response.status_code}: {exc.response.text}"
                ) from exc

        raise RuntimeError(
            f"LM Studio request failed after {self._max_retries} retries"
        ) from last_exc
