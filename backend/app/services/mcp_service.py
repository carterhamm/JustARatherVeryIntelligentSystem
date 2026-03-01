"""
MCP (Model Context Protocol) service for J.A.R.V.I.S.

Provides a high-level interface that routes incoming messages through
the LangGraph agent orchestrator and returns structured MCP responses.
Also supports direct tool execution and capability discovery.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
from uuid import uuid4

from app.agents.orchestrator import run_agent
from app.agents.state import AgentState
from app.agents.tools import get_tool_descriptions, get_tool_registry
from app.schemas.mcp import MCPCapability, MCPResponse, MCPToolCall

logger = logging.getLogger("jarvis.services.mcp")


class MCPService:
    """Facade that wires MCP requests into the agent system."""

    def __init__(
        self,
        agent_graph: Any = None,
        knowledge_service: Any = None,
        chat_service: Any = None,
    ) -> None:
        # Optional injected dependencies; fall back to module-level
        # defaults when not provided (useful during bootstrap).
        self._agent_graph = agent_graph
        self._knowledge_service = knowledge_service
        self._chat_service = chat_service

    # ── Core message processing ───────────────────────────────────────

    async def process_request(
        self,
        user_id: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> MCPResponse:
        """Route a user message through the agent orchestrator.

        Parameters
        ----------
        user_id : str
            Authenticated user UUID (string form).
        message : str
            The user's natural-language message.
        context : dict, optional
            Extra context (conversation_id, system_prompt, etc.).

        Returns
        -------
        MCPResponse
            Structured response including tool-call records, sources,
            and metadata.
        """
        context = context or {}
        conversation_id = context.get("conversation_id", str(uuid4()))

        # Build initial agent state
        state: AgentState = {
            "messages": self._build_messages(message, context),
            "current_plan": "",
            "retrieved_context": "",
            "tool_results": [],
            "final_response": "",
            "user_id": user_id,
            "conversation_id": conversation_id,
            "error": None,
            "metadata": {
                "model": context.get("model"),
                "request_id": str(uuid4()),
            },
        }

        start_ts = time.monotonic()
        result_state = await run_agent(state)
        elapsed_ms = round((time.monotonic() - start_ts) * 1000, 2)

        # Build tool call records
        tool_calls: list[MCPToolCall] = []
        for tr in result_state.get("tool_results", []):
            tool_calls.append(MCPToolCall(
                tool=tr.get("tool", ""),
                params=tr.get("params", {}),
                result=tr.get("result"),
                status=tr.get("status", "unknown"),
            ))

        # Build sources from retrieved context (simplified)
        sources: list[dict[str, Any]] = []
        retrieved = result_state.get("retrieved_context", "")
        if retrieved:
            # Each source block is delimited by "---"
            for block in retrieved.split("\n\n---\n\n"):
                block = block.strip()
                if block:
                    sources.append({"text": block[:500], "type": "knowledge_base"})

        return MCPResponse(
            response=result_state.get("final_response", ""),
            tool_calls=tool_calls if tool_calls else None,
            sources=sources if sources else None,
            metadata={
                "conversation_id": conversation_id,
                "route": result_state.get("metadata", {}).get("route"),
                "latency_ms": elapsed_ms,
                "request_id": result_state.get("metadata", {}).get("request_id"),
                "error": result_state.get("error"),
            },
        )

    # ── Capability listing ────────────────────────────────────────────

    async def get_capabilities(self) -> list[MCPCapability]:
        """Return a list of all tools the agent system can invoke."""
        descriptions = get_tool_descriptions()
        capabilities: list[MCPCapability] = []
        for desc in descriptions:
            capabilities.append(MCPCapability(
                name=desc["name"],
                description=desc["description"],
                parameters=_infer_parameters(desc["name"]),
            ))
        return capabilities

    # ── Direct tool execution ─────────────────────────────────────────

    async def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a tool directly, bypassing the planner/retriever.

        Returns a dict with ``tool``, ``result``, ``status``, and
        ``duration_ms``.
        """
        registry = get_tool_registry()
        tool = registry.get(tool_name)
        if tool is None:
            return {
                "tool": tool_name,
                "result": f"Unknown tool: {tool_name}",
                "status": "error",
                "duration_ms": 0,
            }

        # Build minimal state for tool context
        state: AgentState = {
            "messages": [],
            "current_plan": "",
            "retrieved_context": "",
            "tool_results": [],
            "final_response": "",
            "user_id": user_id or "",
            "conversation_id": "",
            "error": None,
            "metadata": {},
        }

        start_ts = time.monotonic()
        try:
            result = await tool.execute(params, state=state)
            elapsed = round((time.monotonic() - start_ts) * 1000, 2)
            return {
                "tool": tool_name,
                "result": result,
                "status": "success",
                "duration_ms": elapsed,
            }
        except Exception as exc:
            elapsed = round((time.monotonic() - start_ts) * 1000, 2)
            logger.exception("Direct tool execution failed: %s", exc)
            return {
                "tool": tool_name,
                "result": f"Error: {exc}",
                "status": "error",
                "duration_ms": elapsed,
            }

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_messages(
        message: str,
        context: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Build the initial message list for the agent state."""
        messages: list[dict[str, str]] = []

        # Inject system prompt if provided
        system_prompt = context.get("system_prompt")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Inject prior conversation history if provided
        history = context.get("history", [])
        for msg in history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        # The current user message
        messages.append({"role": "user", "content": message})
        return messages


# ── Parameter inference helper ───────────────────────────────────────

def _infer_parameters(tool_name: str) -> dict[str, Any]:
    """Return a simplified JSON-schema-like dict for a tool's params.

    In a production system this would be derived from actual Pydantic
    models or function signatures.  Here we provide hand-authored
    schemas for each known tool.
    """
    schemas: dict[str, dict[str, Any]] = {
        "search_knowledge": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        "send_email": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        "read_email": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
        },
        "create_calendar_event": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string", "format": "date-time"},
                "end": {"type": "string", "format": "date-time"},
                "description": {"type": "string"},
            },
            "required": ["title", "start", "end"],
        },
        "list_calendar_events": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
            },
            "required": ["start_date", "end_date"],
        },
        "set_reminder": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "remind_at": {"type": "string", "format": "date-time"},
            },
            "required": ["message", "remind_at"],
        },
        "smart_home_control": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "command": {"type": "string", "enum": [
                    "on", "off", "set_brightness", "set_temperature",
                    "lock", "unlock", "set_color",
                ]},
                "params": {"type": "object"},
            },
            "required": ["device_id", "command"],
        },
        "web_search": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
        "calculator": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
            },
            "required": ["expression"],
        },
        "date_time": {
            "type": "object",
            "properties": {
                "timezone": {"type": "string", "default": "UTC"},
                "operation": {"type": "string", "enum": ["now", "convert"]},
            },
        },
    }
    return schemas.get(tool_name, {"type": "object", "properties": {}})
