"""
LangGraph StateGraph orchestrator for J.A.R.V.I.S.

Wires together the planner, retriever, executor, and responder nodes
into a compiled graph with conditional routing so that only the nodes
required for a given request are executed.

Graph topology::

    START
      |
    planner
      |-----(respond)---------> responder --> END
      |-----(retrieve)--------> retriever --> responder --> END
      |-----(tools)-----------> executor  --> responder --> END
      |-----(retrieve_and_tools)-> retriever --> executor --> responder --> END
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import (
    AgentState,
    ROUTE_RESPOND,
    ROUTE_RETRIEVE,
    ROUTE_RETRIEVE_AND_TOOLS,
    ROUTE_TOOLS,
)

logger = logging.getLogger("jarvis.agents.orchestrator")


# ═════════════════════════════════════════════════════════════════════════
# Graph construction
# ═════════════════════════════════════════════════════════════════════════

def create_agent_graph():
    """Build and compile the multi-agent StateGraph.

    Returns a LangGraph ``CompiledGraph`` ready for invocation via
    ``await graph.ainvoke(state)``.
    """
    from app.agents.planner import planner_node
    from app.agents.retriever import retriever_node
    from app.agents.executor import executor_node
    from app.agents.responder import responder_node

    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────
    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("executor", executor_node)
    graph.add_node("responder", responder_node)

    # ── Entry edge ────────────────────────────────────────────────────
    graph.add_edge(START, "planner")

    # ── Conditional edges from planner ────────────────────────────────
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "retriever": "retriever",
            "executor": "executor",
            "responder": "responder",
        },
    )

    # ── Conditional edges from retriever ──────────────────────────────
    # After retrieval, either proceed to executor (if retrieve_and_tools)
    # or go directly to responder.
    graph.add_conditional_edges(
        "retriever",
        _route_after_retriever,
        {
            "executor": "executor",
            "responder": "responder",
        },
    )

    # ── Unconditional edges ───────────────────────────────────────────
    graph.add_edge("executor", "responder")
    graph.add_edge("responder", END)

    # ── Compile ───────────────────────────────────────────────────────
    compiled = graph.compile()
    logger.info("Agent graph compiled successfully.")
    return compiled


# ═════════════════════════════════════════════════════════════════════════
# Routing functions (used by conditional edges)
# ═════════════════════════════════════════════════════════════════════════

def _route_after_planner(state: AgentState) -> str:
    """Decide which node follows the planner."""
    route = state.get("metadata", {}).get("route", ROUTE_RESPOND)

    if route == ROUTE_RETRIEVE:
        return "retriever"
    elif route == ROUTE_TOOLS:
        return "executor"
    elif route == ROUTE_RETRIEVE_AND_TOOLS:
        return "retriever"  # retriever first, then executor
    else:
        return "responder"


def _route_after_retriever(state: AgentState) -> str:
    """Decide which node follows the retriever."""
    route = state.get("metadata", {}).get("route", ROUTE_RESPOND)

    if route == ROUTE_RETRIEVE_AND_TOOLS:
        return "executor"
    return "responder"


# ═════════════════════════════════════════════════════════════════════════
# High-level runner
# ═════════════════════════════════════════════════════════════════════════

# Module-level cache for the compiled graph
_compiled_graph = None


def _get_graph():
    """Lazily create and cache the compiled agent graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = create_agent_graph()
    return _compiled_graph


async def run_agent(state: AgentState) -> AgentState:
    """Execute the full agent pipeline for the given input state.

    Parameters
    ----------
    state : AgentState
        Must contain at least ``messages`` (with one user message),
        ``user_id``, and ``conversation_id``.

    Returns
    -------
    AgentState
        The fully-populated state including ``final_response``.
    """
    # Ensure required defaults
    state.setdefault("messages", [])
    state.setdefault("current_plan", "")
    state.setdefault("retrieved_context", "")
    state.setdefault("tool_results", [])
    state.setdefault("final_response", "")
    state.setdefault("error", None)
    state.setdefault("metadata", {})

    graph = _get_graph()

    try:
        result = await graph.ainvoke(state)
        logger.info(
            "Agent run completed for conversation %s (route=%s).",
            state.get("conversation_id", "?"),
            result.get("metadata", {}).get("route", "?"),
        )
        return result
    except Exception as exc:
        logger.exception("Agent graph execution failed: %s", exc)
        state["error"] = str(exc)
        state["final_response"] = (
            "I apologise, sir -- an unexpected error occurred while "
            "processing your request.  My systems will recover shortly."
        )
        return state
