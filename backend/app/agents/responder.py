"""
Responder agent node for the J.A.R.V.I.S. orchestrator.

Synthesises a final natural-language response using the original user
message, conversation history, retrieved knowledge context, and tool
execution results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.state import AgentState
from app.integrations.llm import get_llm_client
from app.config import settings

logger = logging.getLogger("jarvis.agents.responder")

# ── JARVIS system prompt ────────────────────────────────────────────────

_RESPONDER_SYSTEM_PROMPT = """\
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a highly
capable AI assistant created by Mr. Stark.  You are helpful, witty,
concise, and technically brilliant.

When answering:
* Be direct and informative.
* If you were given retrieved context, integrate it naturally; cite
  sources when helpful but never fabricate references.
* If tool results are available, summarise them clearly for the user.
* When tool calls failed, acknowledge the failure gracefully and offer
  alternatives.
* Maintain the conversational tone established in the chat history.
* If you genuinely do not know something and have no context, say so.
"""


async def responder_node(state: AgentState) -> dict[str, Any]:
    """Build the final LLM prompt and generate the assistant response.

    Returns a partial state update containing ``final_response``.
    """
    messages = state.get("messages", [])
    retrieved_context = state.get("retrieved_context", "")
    tool_results = state.get("tool_results", [])
    error = state.get("error")

    # ── Assemble LLM messages ─────────────────────────────────────────────
    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": _RESPONDER_SYSTEM_PROMPT},
    ]

    # Include conversation history (last 20 turns)
    for msg in messages[-20:]:
        llm_messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        })

    # Inject retrieved context as a system addendum
    if retrieved_context:
        llm_messages.append({
            "role": "system",
            "content": (
                "The following context was retrieved from the user's "
                "knowledge base.  Use it to inform your response.\n\n"
                f"{retrieved_context}"
            ),
        })

    # Inject tool results as a system addendum
    if tool_results:
        formatted_results = _format_tool_results(tool_results)
        llm_messages.append({
            "role": "system",
            "content": (
                "The following tool calls were executed on behalf of the "
                "user.  Incorporate their results into your response.\n\n"
                f"{formatted_results}"
            ),
        })

    # Inject error information if present
    if error:
        llm_messages.append({
            "role": "system",
            "content": (
                f"Note: an error occurred during processing: {error}\n"
                "Acknowledge this gracefully if relevant."
            ),
        })

    # ── Call LLM ──────────────────────────────────────────────────────────
    try:
        provider = state.get("metadata", {}).get("llm_provider")
        llm = get_llm_client(provider)
        result = await llm.chat_completion(
            messages=llm_messages,
            temperature=0.7,
            max_tokens=2048,
        )
        final_response = result.get("content", "").strip()
    except Exception as exc:
        logger.exception("Responder LLM call failed: %s", exc)
        final_response = (
            "I apologise, sir -- I encountered a temporary issue generating "
            "my response.  Please try again in a moment."
        )

    return {"final_response": final_response}


# ── Helpers ──────────────────────────────────────────────────────────────

def _format_tool_results(results: list[dict[str, Any]]) -> str:
    """Render tool results into a readable text block for the LLM."""
    parts: list[str] = []
    for i, tr in enumerate(results, start=1):
        tool = tr.get("tool", "unknown")
        status = tr.get("status", "unknown")
        result_text = tr.get("result", "")
        duration = tr.get("duration_ms", 0)

        header = f"[Tool {i}: {tool}] (status={status}, {duration:.0f}ms)"
        parts.append(f"{header}\n{result_text}")

    return "\n\n".join(parts)
