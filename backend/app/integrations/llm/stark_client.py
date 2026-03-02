"""Stark Protocol LLM client — Gemma 3 27B on RunPod serverless.

Submits inference jobs to a RunPod serverless vLLM endpoint and polls
for completion.  Handles cold starts (30-60 s) with a 120 s timeout
and exponential-backoff polling.
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

_MODEL_NAME = "gemma-3-27b"

# Polling configuration
_POLL_INITIAL_INTERVAL = 0.1   # 100 ms
_POLL_MAX_INTERVAL = 2.0       # 2 s
_POLL_BACKOFF_FACTOR = 2.0
_JOB_TIMEOUT = 600.0           # 10 min total (covers cold starts + model loading)

# Retry on transient HTTP errors
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


def _build_prompt(messages: list[dict[str, str]]) -> str:
    """Convert chat messages into a single prompt string for vLLM."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"<start_of_turn>system\n{content}<end_of_turn>")
        elif role == "assistant":
            parts.append(f"<start_of_turn>model\n{content}<end_of_turn>")
        else:
            parts.append(f"<start_of_turn>user\n{content}<end_of_turn>")
    parts.append("<start_of_turn>model\n")
    return "\n".join(parts)


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
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """POST to /run — returns the job ID."""
        payload = {
            "input": {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
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
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Submit + poll with retries on transient errors."""
        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                job_id = await self._submit_job(prompt, temperature, max_tokens)
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
    def _extract_output(data: dict[str, Any]) -> str:
        """Extract generated text from RunPod job output."""
        output = data.get("output")
        if output is None:
            return ""
        # vLLM serverless output formats vary
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            # {"text": "..."} or {"choices": [{"text": "..."}]}
            if "text" in output:
                return output["text"]
            choices = output.get("choices", [])
            if choices:
                return choices[0].get("text", "")
        if isinstance(output, list) and output:
            first = output[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("text", first.get("generated_text", ""))
        return str(output)

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

        prompt = _build_prompt(messages)
        start = time.monotonic()
        data = await self._run_job(prompt, temperature, max_tokens or 1024)
        latency = time.monotonic() - start

        content = self._extract_output(data)
        logger.info("Stark Protocol response: %.1fs, %d chars", latency, len(content))

        return {
            "content": content,
            "model": _MODEL_NAME,
            "usage": {
                "prompt_tokens": max(1, len(prompt) // 4),
                "completion_tokens": max(1, len(content) // 4),
                "total_tokens": max(1, (len(prompt) + len(content)) // 4),
            },
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
                    logger.info("RunPod endpoint healthy")
                    return True
                # RunPod may not have /health — try submitting a tiny job
                job_id = await self._submit_job("Hi", temperature=0.0, max_tokens=5)
                await self._poll_job(job_id)
                logger.info("RunPod endpoint healthy (test job succeeded)")
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
