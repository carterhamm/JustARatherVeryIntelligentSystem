"""
Pydantic v2 schemas for the J.A.R.V.I.S. Model Context Protocol (MCP) layer.

These schemas define the request/response contracts for the MCP API
endpoints that expose the agent system's capabilities to external
consumers (IDE plugins, CLI tools, other LLM agents, etc.).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════════
# Request schemas
# ═════════════════════════════════════════════════════════════════════════

class MCPRequest(BaseModel):
    """Inbound message to be processed by the J.A.R.V.I.S. agent system."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        min_length=1,
        description="The natural-language message or instruction.",
    )
    context: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "Optional context dict -- may include conversation_id, "
            "system_prompt, model override, or arbitrary metadata."
        ),
    )
    tools: Optional[list[str]] = Field(
        None,
        description=(
            "Restrict the agent to only these tool names.  "
            "When ``None`` all tools are available."
        ),
    )


# ═════════════════════════════════════════════════════════════════════════
# Response schemas
# ═════════════════════════════════════════════════════════════════════════

class MCPToolCall(BaseModel):
    """Record of a single tool invocation within an MCP interaction."""

    model_config = ConfigDict(extra="allow")

    tool: str = Field(..., description="Tool name that was invoked.")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters passed to the tool.",
    )
    result: Optional[str] = Field(
        None, description="Tool output (text)."
    )
    status: str = Field(
        "pending",
        description='Execution status: "success", "error", "timeout", or "pending".',
    )


class MCPResponse(BaseModel):
    """Structured response from the J.A.R.V.I.S. agent system."""

    model_config = ConfigDict(extra="allow")

    response: str = Field(
        ...,
        description="The natural-language response from the assistant.",
    )
    tool_calls: Optional[list[MCPToolCall]] = Field(
        None,
        description="Tool calls that were executed (if any).",
    )
    sources: Optional[list[dict[str, Any]]] = Field(
        None,
        description="Knowledge-base sources that informed the response.",
    )
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Additional metadata (route taken, latency, etc.).",
    )


# ═════════════════════════════════════════════════════════════════════════
# Capability schema
# ═════════════════════════════════════════════════════════════════════════

class MCPCapability(BaseModel):
    """Describes a single capability (tool) exposed by the MCP layer."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Machine-readable tool name.")
    description: str = Field(
        ...,
        description="Human-readable description of the tool.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-Schema-like parameter specification.",
    )
