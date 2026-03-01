"""
Agent state definitions for the J.A.R.V.I.S. multi-agent orchestrator.

Defines the shared state schema used by every node in the LangGraph
state-machine.  The state flows through planner -> retriever -> executor
-> responder, accumulating context at each step.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed between every node in the agent graph.

    Fields
    ------
    messages : list[dict]
        Conversation history. Each dict has at minimum ``role`` and ``content``.
    current_plan : str
        JSON-encoded plan produced by the planner node.  Contains the
        ``action`` field (``"retrieve"``, ``"tools"``, ``"respond"``,
        ``"retrieve_and_tools"``) plus supporting details.
    retrieved_context : str
        Textual context assembled by the retriever node from the
        knowledge base (Qdrant + Neo4j).
    tool_results : list[dict]
        Results collected by the executor node.  Each dict contains
        ``tool``, ``params``, ``result``, and ``status``.
    final_response : str
        The fully-formed natural language response from the responder.
    user_id : str
        Authenticated user identifier (UUID as string).
    conversation_id : str
        Active conversation identifier (UUID as string).
    error : str | None
        If a node encounters a non-fatal error it records the message
        here rather than raising.
    metadata : dict
        Arbitrary key/value bag for routing hints, performance counters,
        model overrides, etc.
    """

    messages: list[dict[str, Any]]
    current_plan: str
    retrieved_context: str
    tool_results: list[dict[str, Any]]
    final_response: str
    user_id: str
    conversation_id: str
    error: Optional[str]
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Routing constants (used by planner + conditional edges)
# ---------------------------------------------------------------------------

ROUTE_RETRIEVE: str = "retrieve"
ROUTE_TOOLS: str = "tools"
ROUTE_RESPOND: str = "respond"
ROUTE_RETRIEVE_AND_TOOLS: str = "retrieve_and_tools"

VALID_ROUTES: frozenset[str] = frozenset(
    {ROUTE_RETRIEVE, ROUTE_TOOLS, ROUTE_RESPOND, ROUTE_RETRIEVE_AND_TOOLS}
)
