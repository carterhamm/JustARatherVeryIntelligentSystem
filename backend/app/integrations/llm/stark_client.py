"""Stark Protocol LLM client — Gemma 3 via OpenAI-compatible API.

Connects to an OpenAI-compatible inference server (Modal/vLLM, LM Studio, etc.).
Supports both streaming and non-streaming chat completions.
Handles reconnection on transient failures (e.g. cold starts, sleep/wake).
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
_DEFAULT_MODEL = "gemma-3-12b-it-abliterated"

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
        self._is_remote = not any(
            h in endpoint_url for h in ("localhost", "127.0.0.1", "0.0.0.0")
        )
        # Remote (Modal/cloud): long timeouts for cold starts.
        # Local (LM Studio): short connect timeout.
        connect_timeout = 120.0 if self._is_remote else 5.0
        read_timeout = 300.0 if self._is_remote else 90.0
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
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
        import asyncio
        import json as json_mod

        payload = {
            "model": model or _DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
            "stream": True,
        }

        url = f"{self._endpoint_url}/chat/completions"
        # Remote (tunnel): generous connect timeout for Cloudflare hops.
        # Local: near-instant connection expected.
        connect = 30.0 if self._is_remote else 5.0
        stream_timeout = httpx.Timeout(90.0, connect=connect)

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                async with self._http.stream(
                    "POST", url, json=payload, timeout=stream_timeout,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            return

                        try:
                            chunk = json_mod.loads(data_str)
                        except json_mod.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                    return  # Stream completed successfully

            except httpx.ConnectError as exc:
                # LM Studio isn't running — fail immediately, don't retry
                raise RuntimeError(
                    "Cannot connect to LM Studio at "
                    f"{self._endpoint_url}. Is it running?"
                ) from exc

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "LM Studio stream error (%s), attempt %d/%d — retry in %.1fs",
                    type(exc).__name__, attempt + 1, self._max_retries, delay,
                )
                await asyncio.sleep(delay)

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (502, 503, 504) and attempt < self._max_retries - 1:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "LM Studio returned HTTP %d, attempt %d/%d — retry in %.1fs",
                        exc.response.status_code, attempt + 1, self._max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise RuntimeError(
                        f"LM Studio returned HTTP {exc.response.status_code}"
                    ) from exc

        raise RuntimeError(
            f"LM Studio not responding after {self._max_retries} attempts. "
            "Check that LM Studio is running and has a model loaded."
        )

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
        """Check if Stark Protocol endpoint is running and responsive."""
        import asyncio
        # Use a short timeout for health checks — don't block app startup
        health_timeout = httpx.Timeout(10.0, connect=5.0)
        for attempt in range(retries):
            try:
                resp = await self._http.get(
                    f"{self._endpoint_url}/models",
                    timeout=health_timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        model_ids = [m.get("id", "unknown") for m in models]
                        logger.info("Stark Protocol healthy, models: %s", model_ids)
                    else:
                        logger.info("Stark Protocol healthy, no models loaded")
                    return True
            except Exception as exc:
                logger.warning(
                    "Stark Protocol health check %d/%d failed: %s",
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
            except httpx.ConnectError as exc:
                if self._is_remote:
                    # Remote: might be a transient network issue, retry
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Stark Protocol connect error, attempt %d/%d — retry in %.1fs",
                        attempt + 1, self._max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise RuntimeError(
                        "Cannot connect to Stark Protocol at "
                        f"{self._endpoint_url}. Is the server running?"
                    ) from exc
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Stark Protocol request error (%s), attempt %d/%d — retry in %.1fs",
                    type(exc).__name__, attempt + 1, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (502, 503, 504) and attempt < self._max_retries - 1:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Stark Protocol HTTP %d, attempt %d/%d — retry in %.1fs",
                        exc.response.status_code, attempt + 1, self._max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise RuntimeError(
                        f"Stark Protocol error {exc.response.status_code}: {exc.response.text}"
                    ) from exc

        raise RuntimeError(
            "Stark Protocol not responding after retries. "
            "The server may be starting up (cold start). Try again in a minute."
        ) from last_exc
