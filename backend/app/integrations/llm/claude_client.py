"""Anthropic Claude LLM client.

Handles the Anthropic API's unique system message format: the ``system``
parameter is a top-level kwarg, not a message with role ``"system"``.

Supports native tool use for agentic workflows.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Optional

from anthropic import AsyncAnthropic, APIConnectionError, APITimeoutError, RateLimitError

from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.claude")

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Max tool use iterations to prevent infinite loops
_MAX_TOOL_TURNS = 10


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

    # ═══════════════════════════════════════════════════════════════════════
    # Tool-use aware streaming (agentic mode)
    # ═══════════════════════════════════════════════════════════════════════

    async def agentic_stream(
        self,
        messages: list[dict],
        tools: list[dict[str, Any]],
        tool_executor,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a response with automatic tool use loop.

        Yields event dicts:
            {"type": "text", "content": "..."}
            {"type": "tool_use_start", "tool": "...", "tool_use_id": "...", "input": {...}}
            {"type": "tool_result", "tool": "...", "result": "..."}
            {"type": "done"}
            {"type": "error", "error": "..."}

        Parameters
        ----------
        messages : list[dict]
            Conversation messages (system/user/assistant). May include
            content blocks for multi-turn tool use.
        tools : list[dict]
            Anthropic tool definitions.
        tool_executor : callable
            Async function: (tool_name, tool_input) -> str
        """
        system_text, api_messages = self._extract_system_rich(messages)
        model = model or self.default_model

        for turn in range(_MAX_TOOL_TURNS):
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 4096,
                "tools": tools,
            }
            if system_text:
                kwargs["system"] = system_text

            # Accumulate the full response content blocks
            text_content = ""
            tool_uses: list[dict] = []
            response_content_blocks: list[dict] = []

            try:
                async with self._client.messages.stream(**kwargs) as stream:
                    current_tool_use: dict | None = None
                    current_tool_input_json = ""

                    async for event in stream:
                        # Handle different event types from the raw stream
                        if event.type == "content_block_start":
                            block = event.content_block
                            if block.type == "text":
                                pass  # text deltas come in content_block_delta
                            elif block.type == "tool_use":
                                current_tool_use = {
                                    "id": block.id,
                                    "name": block.name,
                                }
                                current_tool_input_json = ""

                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                text_content += delta.text
                                yield {"type": "text", "content": delta.text}
                            elif delta.type == "input_json_delta":
                                current_tool_input_json += delta.partial_json

                        elif event.type == "content_block_stop":
                            if current_tool_use is not None:
                                try:
                                    tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                                except json.JSONDecodeError:
                                    tool_input = {}
                                current_tool_use["input"] = tool_input
                                tool_uses.append(current_tool_use)
                                response_content_blocks.append({
                                    "type": "tool_use",
                                    "id": current_tool_use["id"],
                                    "name": current_tool_use["name"],
                                    "input": tool_input,
                                })
                                current_tool_use = None
                                current_tool_input_json = ""

                    # Get the final message for stop_reason
                    final_message = await stream.get_final_message()
                    stop_reason = final_message.stop_reason

            except _RETRYABLE_ERRORS as exc:
                logger.error("Claude agentic stream error: %s", exc)
                yield {"type": "error", "error": str(exc)}
                return

            # Add any text content to response blocks
            if text_content:
                response_content_blocks.insert(0, {
                    "type": "text",
                    "text": text_content,
                })

            # If no tool use, we're done
            if stop_reason != "tool_use" or not tool_uses:
                yield {"type": "done"}
                return

            # Execute tools and prepare for next turn
            api_messages.append({"role": "assistant", "content": response_content_blocks})

            tool_results: list[dict] = []
            for tu in tool_uses:
                yield {
                    "type": "tool_use_start",
                    "tool": tu["name"],
                    "tool_use_id": tu["id"],
                    "input": tu["input"],
                }

                try:
                    result = await tool_executor(tu["name"], tu["input"])
                except Exception as exc:
                    logger.exception("Tool execution failed: %s", tu["name"])
                    result = f"Tool error: {exc}"

                yield {
                    "type": "tool_result",
                    "tool": tu["name"],
                    "result": result[:500],  # truncate for display
                }

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": result,
                })

            api_messages.append({"role": "user", "content": tool_results})

        # Exhausted max turns
        yield {"type": "text", "content": "\n\n*Reached maximum tool use depth.*"}
        yield {"type": "done"}

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════

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
                if isinstance(content, str) and content.strip():
                    system_parts.append(content.strip())
            else:
                remaining.append({"role": role, "content": content})

        return "\n\n".join(system_parts), remaining

    @staticmethod
    def _extract_system_rich(
        messages: list[dict],
    ) -> tuple[str, list[dict]]:
        """Like _extract_system but preserves rich content blocks.

        Messages may contain content block lists (for tool use) instead
        of plain strings. System messages are still extracted as text.
        """
        system_parts: list[str] = []
        remaining: list[dict] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                if isinstance(content, str) and content.strip():
                    system_parts.append(content.strip())
            else:
                remaining.append({"role": role, "content": content})

        return "\n\n".join(system_parts), remaining
