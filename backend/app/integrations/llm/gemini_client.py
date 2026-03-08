"""Google Gemini LLM client.

Uses the ``google-genai`` SDK.  Handles role mapping: the Gemini API
uses ``"model"`` where OpenAI uses ``"assistant"``.

Supports native function calling for agentic workflows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Callable, Optional

from google import genai
from google.genai import types

from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.gemini")

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0

# Max tool use iterations to prevent infinite loops
_MAX_TOOL_TURNS = 10


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
        **kwargs,
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

        # Optional tool use support for non-streaming path
        tools = kwargs.get("tools")
        tool_executor = kwargs.get("tool_executor")
        if tools:
            gemini_tools = self._convert_tools_to_gemini(tools)
            config.tools = gemini_tools

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )

                # Check for function calls and execute if we have a tool_executor
                if tool_executor and response.candidates:
                    candidate = response.candidates[0]
                    function_calls = [
                        p for p in (candidate.content.parts or [])
                        if p.function_call is not None
                    ]

                    turn = 0
                    while function_calls and turn < _MAX_TOOL_TURNS:
                        turn += 1
                        # Add assistant response to contents
                        contents.append(candidate.content)

                        # Execute each function call and build responses
                        function_response_parts = []
                        for part in function_calls:
                            fc = part.function_call
                            try:
                                result = await tool_executor(
                                    fc.name, dict(fc.args) if fc.args else {}
                                )
                            except Exception as exc:
                                logger.exception("Tool execution failed: %s", fc.name)
                                result = f"Tool error: {exc}"

                            function_response_parts.append(
                                types.Part.from_function_response(
                                    name=fc.name,
                                    response={"result": result},
                                )
                            )

                        # Send function responses back
                        contents.append(
                            types.Content(
                                role="user",
                                parts=function_response_parts,
                            )
                        )

                        response = await self._client.aio.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=config,
                        )

                        if response.candidates:
                            candidate = response.candidates[0]
                            function_calls = [
                                p for p in (candidate.content.parts or [])
                                if p.function_call is not None
                            ]
                        else:
                            function_calls = []

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

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                stream = await self._client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                async for chunk in stream:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as exc:
                last_exc = exc
                delay = self._retry_base_delay * (2 ** attempt)
                logger.warning(
                    "Gemini stream failed (attempt %d/%d): %s [%s] — retry in %.1fs",
                    attempt + 1, self._max_retries,
                    type(exc).__name__, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Gemini stream failed after {self._max_retries} retries: {last_exc}"
        ) from last_exc

    # ═══════════════════════════════════════════════════════════════════════
    # Tool-use aware streaming (agentic mode)
    # ═══════════════════════════════════════════════════════════════════════

    async def agentic_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        tool_executor: Callable,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a response with automatic function calling loop.

        Yields event dicts matching the Claude agentic_stream interface:
            {"type": "text", "content": "..."}
            {"type": "tool_use_start", "tool": "...", "tool_use_id": "...", "input": {...}}
            {"type": "tool_result", "tool": "...", "result": "..."}
            {"type": "done"}
            {"type": "error", "error": "..."}

        Parameters
        ----------
        messages : list[dict]
            Conversation messages (system/user/assistant).
        tools : list[dict]
            Anthropic-format tool definitions (converted internally).
        tool_executor : callable
            Async function: (tool_name, tool_input) -> str
        model : str, optional
            Model override.
        temperature : float
            Sampling temperature.
        max_tokens : int, optional
            Max output tokens.
        """
        system_text, contents = self._prepare_messages(messages)
        model_name = model or self.default_model

        # Convert Anthropic-format tools to Gemini function declarations
        gemini_tools = self._convert_tools_to_gemini(tools)

        config = types.GenerateContentConfig(
            temperature=temperature,
            tools=gemini_tools,
        )
        if max_tokens is not None:
            config.max_output_tokens = max_tokens
        if system_text:
            config.system_instruction = system_text

        for turn in range(_MAX_TOOL_TURNS):
            # Use non-streaming for tool-calling turns so we get the full
            # response with all function_call parts at once
            last_exc: BaseException | None = None
            response = None

            for attempt in range(self._max_retries):
                try:
                    response = await self._client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    delay = self._retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "Gemini agentic request failed (attempt %d/%d): %s — retry in %.1fs",
                        attempt + 1, self._max_retries,
                        type(exc).__name__, delay,
                    )
                    await asyncio.sleep(delay)

            if response is None:
                yield {
                    "type": "error",
                    "error": f"Gemini request failed after {self._max_retries} retries: {last_exc}",
                }
                return

            # Extract parts from the response
            if not response.candidates:
                yield {"type": "error", "error": "No candidates in Gemini response"}
                return

            candidate = response.candidates[0]
            parts = candidate.content.parts or []

            # Separate text parts and function call parts
            text_parts: list[str] = []
            function_calls: list[tuple[str, dict]] = []

            for part in parts:
                if part.function_call is not None:
                    fc = part.function_call
                    function_calls.append((
                        fc.name,
                        dict(fc.args) if fc.args else {},
                    ))
                elif part.text:
                    text_parts.append(part.text)

            # If there are no function calls, this is the final turn —
            # stream the text response for a better UX
            if not function_calls:
                if text_parts:
                    # We already have the text from the non-streaming call,
                    # yield it as text events
                    combined_text = "".join(text_parts)
                    # Yield in chunks for a streaming feel
                    chunk_size = 12  # ~3 words per chunk
                    for i in range(0, len(combined_text), chunk_size):
                        yield {
                            "type": "text",
                            "content": combined_text[i:i + chunk_size],
                        }
                yield {"type": "done"}
                return

            # Yield any interleaved text before tool calls
            if text_parts:
                for tp in text_parts:
                    yield {"type": "text", "content": tp}

            # Add the model's response to the conversation
            contents.append(candidate.content)

            # Execute each function call
            function_response_parts = []
            for fc_name, fc_args in function_calls:
                tool_use_id = f"gemini_{uuid.uuid4().hex[:12]}"

                yield {
                    "type": "tool_use_start",
                    "tool": fc_name,
                    "tool_use_id": tool_use_id,
                    "input": fc_args,
                }

                try:
                    result = await tool_executor(fc_name, fc_args)
                except Exception as exc:
                    logger.exception("Tool execution failed: %s", fc_name)
                    result = f"Tool error: {exc}"

                yield {
                    "type": "tool_result",
                    "tool": fc_name,
                    "result": result[:500],  # truncate for display
                }

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=fc_name,
                        response={"result": result},
                    )
                )

            # Send function responses back to Gemini
            contents.append(
                types.Content(
                    role="user",
                    parts=function_response_parts,
                )
            )

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
        # Gemini uses roughly 4 chars per token
        return max(1, len(text) // 4)

    def get_cheap_model(self) -> str:
        return "gemini-3.1-flash-lite-preview"

    @staticmethod
    def _convert_tools_to_gemini(
        anthropic_tools: list[dict[str, Any]],
    ) -> list[types.Tool]:
        """Convert Anthropic-format tool schemas to Gemini FunctionDeclarations.

        Anthropic format:
            {"name": "...", "description": "...", "input_schema": {"type": "object", ...}}

        Gemini format:
            types.FunctionDeclaration(name="...", description="...", parameters={...})
        """
        declarations = []
        for tool in anthropic_tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            input_schema = tool.get("input_schema", {})

            # Build the parameters dict — Gemini accepts JSON Schema-like objects
            # but we need to strip unsupported keys and ensure compatibility
            parameters = _sanitize_schema_for_gemini(input_schema) if input_schema else None

            decl = types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=parameters,
            )
            declarations.append(decl)

        return [types.Tool(function_declarations=declarations)]

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


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    """Sanitize a JSON Schema for Gemini's function calling.

    Gemini's function calling is strict about the schema format.
    This strips fields that Gemini doesn't support and ensures
    the schema is compatible.
    """
    sanitized: dict[str, Any] = {}

    if "type" in schema:
        sanitized["type"] = schema["type"].upper()

    if "description" in schema:
        sanitized["description"] = schema["description"]

    if "properties" in schema:
        sanitized["properties"] = {}
        for prop_name, prop_schema in schema["properties"].items():
            sanitized["properties"][prop_name] = _sanitize_property(prop_schema)

    if "required" in schema and schema["required"]:
        sanitized["required"] = schema["required"]

    if "enum" in schema:
        sanitized["enum"] = schema["enum"]

    if "items" in schema:
        sanitized["items"] = _sanitize_property(schema["items"])

    return sanitized


def _sanitize_property(prop: dict) -> dict:
    """Sanitize an individual property schema for Gemini."""
    sanitized: dict[str, Any] = {}

    if "type" in prop:
        sanitized["type"] = prop["type"].upper()

    if "description" in prop:
        sanitized["description"] = prop["description"]

    if "enum" in prop:
        sanitized["enum"] = prop["enum"]

    if "default" in prop:
        # Gemini doesn't support 'default' in function schemas — skip it
        pass

    if "items" in prop:
        sanitized["items"] = _sanitize_property(prop["items"])

    if "properties" in prop:
        sanitized["properties"] = {}
        for name, sub_prop in prop["properties"].items():
            sanitized["properties"][name] = _sanitize_property(sub_prop)

    if "required" in prop and prop["required"]:
        sanitized["required"] = prop["required"]

    return sanitized
