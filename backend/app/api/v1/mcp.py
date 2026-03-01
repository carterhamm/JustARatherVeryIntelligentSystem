"""
MCP (Model Context Protocol) API router for J.A.R.V.I.S.

Exposes the agent system through a clean REST interface compatible
with the Model Context Protocol conventions.

Endpoints
---------
POST /mcp/process           Process a message through the agent system.
GET  /mcp/capabilities      List available tools and capabilities.
POST /mcp/tools/{tool_name} Execute a specific tool directly.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.mcp import MCPCapability, MCPRequest, MCPResponse
from app.services.mcp_service import MCPService

logger = logging.getLogger("jarvis.api.mcp")

router = APIRouter(prefix="/mcp", tags=["MCP"])

# ---------------------------------------------------------------------------
# Dependency: MCPService
# ---------------------------------------------------------------------------

_mcp_service: MCPService | None = None


def _get_mcp_service() -> MCPService:
    """Return (or lazily create) the singleton MCPService."""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = MCPService()
    return _mcp_service


# ═══════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════

@router.post(
    "/process",
    response_model=MCPResponse,
    summary="Process a message through the J.A.R.V.I.S. agent system",
    description=(
        "Send a natural-language message to the multi-agent pipeline. "
        "The system will plan, optionally retrieve knowledge and execute "
        "tools, then return a structured response."
    ),
)
async def process_message(
    request: MCPRequest,
    current_user: User = Depends(get_current_active_user),
    svc: MCPService = Depends(_get_mcp_service),
) -> MCPResponse:
    """Process a message through the full agent pipeline."""
    user_id = str(current_user.id)
    try:
        response = await svc.process_request(
            user_id=user_id,
            message=request.message,
            context=request.context,
        )
        return response
    except Exception as exc:
        logger.exception("MCP process_message failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent processing failed: {exc}",
        )


@router.get(
    "/capabilities",
    response_model=list[MCPCapability],
    summary="List available agent capabilities",
    description="Returns a list of all tools the agent system can invoke.",
)
async def list_capabilities(
    current_user: User = Depends(get_current_active_user),
    svc: MCPService = Depends(_get_mcp_service),
) -> list[MCPCapability]:
    """Return all registered tool capabilities."""
    return await svc.get_capabilities()


@router.post(
    "/tools/{tool_name}",
    summary="Execute a specific tool directly",
    description=(
        "Bypass the planner and invoke a tool by name with the given "
        "parameters.  Useful for programmatic integrations."
    ),
)
async def execute_tool(
    tool_name: str,
    params: dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    svc: MCPService = Depends(_get_mcp_service),
) -> dict[str, Any]:
    """Execute a single tool directly."""
    user_id = str(current_user.id)
    result = await svc.execute_tool(
        tool_name=tool_name,
        params=params,
        user_id=user_id,
    )
    if result.get("status") == "error" and "Unknown tool" in result.get("result", ""):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found.",
        )
    return result
