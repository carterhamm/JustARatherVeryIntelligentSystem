"""Stark Protocol LLM client — Gemma 3 27B on RunPod serverless vLLM.

Submits inference jobs to a RunPod serverless vLLM endpoint using the
OpenAI-compatible chat completions route.  Polls for completion with
exponential-backoff.  Handles cold starts (up to several minutes) with
a 600 s timeout.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Optional

import httpx

from app.integrations.llm.base import BaseLLMClient, LLMProvider
from app.integrations.llm.shield_gemma import ShieldGemmaFilter, FilterResult

logger = logging.getLogger("jarvis.llm.stark_protocol")

_MODEL_NAME = "google/gemma-3-27b-it"

# Polling configuration
_POLL_INITIAL_INTERVAL = 0.5   # 500 ms
_POLL_MAX_INTERVAL = 3.0       # 3 s
_POLL_BACKOFF_FACTOR = 1.5
_JOB_TIMEOUT = 600.0           # 10 min total (covers cold starts + model loading)

# Retry on transient HTTP errors
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


class StarkProtocolClient(BaseLLMClient):
    """Client for Gemma 3 27B running on RunPod serverless vLLM."""

    provider = LLMProvider.STARK_PROTOCOL
    default_model = _MODEL_NAME

    def __init__(
        self,
        endpoint_url: str,
        api_key: str,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._endpoint_url = endpoint_url.rstrip("/")
        self._api_key = api_key
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        self._shield = ShieldGemmaFilter()

    # ------------------------------------------------------------------
    # RunPod job lifecycle
    # ------------------------------------------------------------------

    async def _submit_job(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """POST to /run with vLLM OpenAI-compatible format — returns the job ID."""
        payload = {
            "input": {
                "openai_route": "/v1/chat/completions",
                "openai_input": {
                    "model": _MODEL_NAME,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            },
        }
        resp = await self._http.post(self._endpoint_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("id")
        if not job_id:
            raise RuntimeError(f"RunPod returned no job ID: {data}")
        logger.info("RunPod job submitted: %s", job_id)
        return job_id

    async def _poll_job(self, job_id: str) -> dict[str, Any]:
        """Poll GET /status/{job_id} until COMPLETED or FAILED."""
        status_url = self._endpoint_url.replace("/run", f"/status/{job_id}")
        interval = _POLL_INITIAL_INTERVAL
        start = time.monotonic()

        while True:
            elapsed = time.monotonic() - start
            if elapsed > _JOB_TIMEOUT:
                raise TimeoutError(
                    f"RunPod job {job_id} timed out after {_JOB_TIMEOUT:.0f}s"
                )

            resp = await self._http.get(status_url)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "UNKNOWN")

            if status == "COMPLETED":
                logger.info(
                    "RunPod job %s completed in %.1fs", job_id, elapsed,
                )
                return data

            if status == "FAILED":
                error = data.get("error", "unknown error")
                raise RuntimeError(f"RunPod job {job_id} failed: {error}")

            # IN_QUEUE or IN_PROGRESS — keep polling
            await asyncio.sleep(interval)
            interval = min(interval * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)

    async def _run_job(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Submit + poll with retries on transient errors."""
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                job_id = await self._submit_job(messages, temperature, max_tokens)
                return await self._poll_job(job_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 503:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "RunPod 503 (no workers), attempt %d/%d — retry in %.1fs",
                        attempt + 1, self._max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout, TimeoutError) as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "RunPod transient error (%s), attempt %d/%d — retry in %.1fs",
                    type(exc).__name__, attempt + 1, self._max_retries, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"RunPod request failed after {self._max_retries} retries"
        ) from last_exc

    @staticmethod
    def _extract_output(data: dict[str, Any]) -> tuple[str, dict[str, int]]:
        """Extract generated text and usage from RunPod vLLM job output.

        The vLLM worker wraps OpenAI-format responses in a list:
        {"output": [{"choices": [{"message": {"content": "..."}}], "usage": {...}}]}
        """
        output = data.get("output")
        if output is None:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # vLLM worker returns output as a list of OpenAI responses
        if isinstance(output, list) and output:
            first = output[0]
            if isinstance(first, dict):
                # Extract content from choices
                choices = first.get("choices", [])
                if choices:
                    choice = choices[0]
                    # Chat completion format: choices[].message.content
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    if not content:
                        # Completion format: choices[].text
                        content = choice.get("text", "")
                else:
                    content = ""

                # Extract real usage from vLLM
                usage = first.get("usage", {})
                token_usage = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
                return content, token_usage

        # Fallback for unexpected formats
        if isinstance(output, str):
            return output, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        return str(output), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # ------------------------------------------------------------------
    # BaseLLMClient interface
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
                    "model": _MODEL_NAME,
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "finish_reason": "content_filter",
                    "tool_calls": None,
                }

        start = time.monotonic()
        data = await self._run_job(messages, temperature, max_tokens or 1024)
        latency = time.monotonic() - start

        content, usage = self._extract_output(data)
        logger.info("Stark Protocol response: %.1fs, %d chars", latency, len(content))

        return {
            "content": content,
            "model": _MODEL_NAME,
            "usage": usage,
            "finish_reason": "stop",
            "tool_calls": None,
        }

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        # RunPod serverless is request/response — simulate streaming by
        # yielding the full response in chunks.
        result = await self.chat_completion(messages, model, temperature, max_tokens)
        content = result.get("content", "")
        chunk_size = 20
        for i in range(0, len(content), chunk_size):
            yield content[i : i + chunk_size]

    async def count_tokens(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> int:
        return max(1, len(text) // 4)

    async def health_check(self, retries: int = 2, delay: float = 3.0) -> bool:
        """Check if the RunPod endpoint is reachable."""
        for attempt in range(retries):
            try:
                resp = await self._http.get(
                    self._endpoint_url.replace("/run", "/health"),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    workers = data.get("workers", {})
                    ready = workers.get("ready", 0)
                    logger.info(
                        "RunPod endpoint healthy (%d workers ready)", ready,
                    )
                    return True
            except Exception as exc:
                logger.warning(
                    "RunPod health check %d/%d failed: %s",
                    attempt + 1, retries, exc,
                )
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
        return False

    def get_cheap_model(self) -> str:
        return _MODEL_NAME
