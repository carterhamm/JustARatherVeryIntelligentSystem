"""
Planner agent node for the J.A.R.V.I.S. orchestrator.

Analyses the latest user message (and conversation history) to decide
which downstream nodes should run:

* ``"retrieve"``            -- knowledge-base lookup only
* ``"tools"``               -- one or more tool calls only
* ``"respond"``             -- direct LLM response (no retrieval / tools)
* ``"retrieve_and_tools"``  -- both retrieval and tool execution
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.state import (
    AgentState,
    ROUTE_RESPOND,
    ROUTE_RETRIEVE,
    ROUTE_RETRIEVE_AND_TOOLS,
    ROUTE_TOOLS,
    VALID_ROUTES,
)
from app.integrations.llm_client import LLMClient
from app.config import settings

logger = logging.getLogger("jarvis.agents.planner")

# ── System prompt for the planning step ──────────────────────────────────

_PLANNER_SYSTEM_PROMPT = """\
You are the planning module of J.A.R.V.I.S., an advanced AI assistant.

Given the user's latest message and conversation history, decide which
actions are required to fulfil the request.  Return a JSON object with
the following schema — NO markdown fences, NO extra text:

{
  "action": "<retrieve | tools | respond | retrieve_and_tools>",
  "reasoning": "<one-sentence rationale>",
  "search_query": "<query for knowledge base — only when action includes retrieve>",
  "tool_calls": [
    {
      "tool": "<tool_name>",
      "params": { ... }
    }
  ]
}

## Tool catalogue

- search_knowledge   -- search the private knowledge base
- send_email         -- compose and send an email (params: to, subject, body)
- read_email         -- read recent emails (params: query?, limit?)
- create_calendar_event -- create a calendar event (params: title, start, end, description?)
- list_calendar_events  -- list upcoming events (params: start_date, end_date)
- set_reminder       -- set a reminder (params: message, remind_at)
- smart_home_control -- control a smart-home device (params: device_id, command, params?)
- web_search         -- search the web (params: query)
- calculator         -- evaluate a math expression (params: expression)
- date_time          -- current date/time or timezone conversion (params: timezone?, operation?)

## Decision guide

- Greetings, small talk, or questions you can answer from conversation
  context alone -> "respond"
- Questions about the user's personal data, documents, notes, or past
  conversations -> "retrieve"
- Requests that require interacting with external services (email,
  calendar, smart home, web) -> "tools"
- Complex requests that need both knowledge lookup and tool execution
  -> "retrieve_and_tools"

Always default to "respond" when uncertain.
"""


async def planner_node(state: AgentState) -> dict[str, Any]:
    """Analyse the user message and produce a routing plan.

    Returns a partial state update containing ``current_plan`` (JSON
    string) and ``metadata`` with the ``route`` key consumed by the
    orchestrator's conditional edges.
    """
    messages = state.get("messages", [])
    if not messages:
        return {
            "current_plan": json.dumps({"action": ROUTE_RESPOND, "reasoning": "No messages provided."}),
            "metadata": {**state.get("metadata", {}), "route": ROUTE_RESPOND},
        }

    # Build the LLM prompt --------------------------------------------------
    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
    ]

    # Include recent conversation context (last 10 turns for efficiency)
    for msg in messages[-10:]:
        llm_messages.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        })

    # Call the LLM ----------------------------------------------------------
    try:
        llm = LLMClient(api_key=settings.OPENAI_API_KEY)
        result = await llm.chat_completion(
            messages=llm_messages,
            temperature=0.0,
            max_tokens=512,
        )
        raw_plan = result.get("content", "").strip()
        logger.debug("Planner raw output: %s", raw_plan)

        # Parse the JSON plan -----------------------------------------------
        plan = _parse_plan(raw_plan)
    except Exception as exc:
        logger.exception("Planner LLM call failed: %s", exc)
        plan = {
            "action": ROUTE_RESPOND,
            "reasoning": f"Planner error — falling back to direct response. ({exc})",
        }

    route = plan.get("action", ROUTE_RESPOND)
    if route not in VALID_ROUTES:
        logger.warning("Invalid route '%s' from planner; falling back to respond.", route)
        route = ROUTE_RESPOND
        plan["action"] = route

    return {
        "current_plan": json.dumps(plan),
        "metadata": {**state.get("metadata", {}), "route": route},
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def _parse_plan(raw: str) -> dict[str, Any]:
    """Best-effort JSON parsing of the planner output.

    Handles common LLM quirks (markdown fences, trailing commas, extra
    text before/after the JSON object).
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (possibly with language tag)
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Attempt direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object boundaries
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Absolute fallback
    logger.warning("Could not parse planner output as JSON: %s", raw[:200])
    return {"action": ROUTE_RESPOND, "reasoning": "Failed to parse plan; responding directly."}
