"""Sub-agent definitions and runner for the multi-agent framework.

Each sub-agent has a specialized role, LLM provider, and tool subset.
Sub-agents run as async tasks and return structured results.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("jarvis.sub_agents")


class SubAgentType(str, enum.Enum):
    RESEARCHER = "researcher"
    CODER = "coder"
    QUICK = "quick"
    PLANNER = "planner"


@dataclass
class SubAgentConfig:
    agent_type: SubAgentType
    llm_provider: str  # "gemini", "claude", "stark_protocol"
    model: str
    tool_names: list[str] = field(default_factory=list)
    system_prompt: str = ""
    timeout: float = 45.0


# Sub-agent configurations
SUB_AGENT_CONFIGS: dict[SubAgentType, SubAgentConfig] = {
    SubAgentType.RESEARCHER: SubAgentConfig(
        agent_type=SubAgentType.RESEARCHER,
        llm_provider="gemini",
        model="gemini-2.5-flash-preview-05-20",
        tool_names=[
            "web_search", "perplexity_research", "search_knowledge",
            "wolfram_alpha", "search_contacts",
        ],
        system_prompt=(
            "You are a research specialist sub-agent of J.A.R.V.I.S. "
            "Your job is to gather comprehensive, accurate information using your tools. "
            "Be thorough but concise. Cite sources when possible. "
            "Return your findings as a clear summary — another agent will synthesize your work."
        ),
    ),
    SubAgentType.CODER: SubAgentConfig(
        agent_type=SubAgentType.CODER,
        llm_provider="gemini",
        model="gemini-2.5-flash-preview-05-20",
        tool_names=[
            "github", "mac_mini_exec", "mac_mini_claude_code",
            "web_search", "mac_mini_screenshot",
        ],
        system_prompt=(
            "You are a technical specialist sub-agent of J.A.R.V.I.S. "
            "You handle code analysis, GitHub operations, and technical problem-solving. "
            "Be precise and technical. Return actionable results."
        ),
    ),
    SubAgentType.QUICK: SubAgentConfig(
        agent_type=SubAgentType.QUICK,
        llm_provider="gemini",
        model="gemini-2.5-flash-preview-05-20",
        tool_names=[
            "date_time", "calculator", "weather",
            "mac_weather_current", "mac_weather_forecast",
            "sports", "scripture_lookup", "financial_data",
        ],
        system_prompt=(
            "You are a quick-lookup sub-agent of J.A.R.V.I.S. "
            "Answer factual questions fast using your tools. "
            "Keep responses brief and data-focused."
        ),
        timeout=20.0,
    ),
    SubAgentType.PLANNER: SubAgentConfig(
        agent_type=SubAgentType.PLANNER,
        llm_provider="gemini",
        model="gemini-2.5-flash-preview-05-20",
        tool_names=[
            "mac_calendars_list", "mac_events_fetch", "mac_events_create",
            "mac_reminders_create", "list_calendar_events", "create_calendar_event",
            "search_knowledge", "set_reminder",
        ],
        system_prompt=(
            "You are a planning specialist sub-agent of J.A.R.V.I.S. "
            "You handle scheduling, calendar operations, reminders, and multi-step planning. "
            "Be organized and thorough. Return clear action items and confirmations."
        ),
    ),
}


async def run_sub_agent(
    agent_type: SubAgentType,
    task_description: str,
    user_id: str,
    context: str = "",
) -> dict[str, Any]:
    """Run a sub-agent with its specialized LLM and tools.

    Returns a result dict with agent_type, result text, status, and timing.
    """
    import asyncio

    config = SUB_AGENT_CONFIGS[agent_type]
    start = time.perf_counter()

    try:
        result_text = await asyncio.wait_for(
            _execute_sub_agent(config, task_description, user_id, context),
            timeout=config.timeout,
        )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Sub-agent %s completed in %.0fms",
            agent_type.value, duration_ms,
        )
        return {
            "agent_type": agent_type.value,
            "task": task_description,
            "result": result_text,
            "status": "success",
            "duration_ms": round(duration_ms),
        }
    except asyncio.TimeoutError:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.warning("Sub-agent %s timed out after %.0fms", agent_type.value, duration_ms)
        return {
            "agent_type": agent_type.value,
            "task": task_description,
            "result": f"Sub-agent timed out after {config.timeout}s",
            "status": "timeout",
            "duration_ms": round(duration_ms),
        }
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("Sub-agent %s failed: %s", agent_type.value, exc)
        return {
            "agent_type": agent_type.value,
            "task": task_description,
            "result": f"Sub-agent error: {exc}",
            "status": "error",
            "duration_ms": round(duration_ms),
        }


async def _execute_sub_agent(
    config: SubAgentConfig,
    task: str,
    user_id: str,
    context: str,
) -> str:
    """Internal: run the LLM with filtered tools for a sub-agent."""
    from app.agents.tool_schemas import get_anthropic_tools
    from app.agents.tools import get_tool_registry
    from app.integrations.llm.factory import get_llm_client

    # Get LLM client
    try:
        llm = get_llm_client(config.llm_provider)
    except Exception:
        logger.warning(
            "LLM provider %s unavailable, falling back to gemini",
            config.llm_provider,
        )
        llm = get_llm_client("gemini")

    # Filter tools to only those allowed for this sub-agent
    all_tools = get_anthropic_tools()
    tools = [t for t in all_tools if t.get("name") in config.tool_names]
    if not tools:
        tools = []  # No tools needed for some simple sub-agents

    registry = get_tool_registry()

    async def execute_tool(name: str, params: dict) -> str:
        tool = registry.get(name)
        if not tool:
            return f"Unknown tool: {name}"
        if name not in config.tool_names:
            return f"Tool {name} not available to this sub-agent"
        state = {"user_id": user_id}
        return await tool.run(params, state=state)

    # Build messages
    messages = [
        {"role": "system", "content": config.system_prompt},
    ]
    if context:
        messages.append({"role": "user", "content": f"Context from other agents:\n{context}"})
    messages.append({"role": "user", "content": task})

    # Run agentic stream and collect result
    collected: list[str] = []
    if hasattr(llm, "agentic_stream") and tools:
        async for event in llm.agentic_stream(
            messages=messages,
            tools=tools,
            tool_executor=execute_tool,
            model=config.model,
        ):
            if event.get("type") == "text":
                collected.append(event["content"])
    else:
        # Fallback to simple chat completion
        response = await llm.chat_completion(
            messages=messages,
            model=config.model,
        )
        collected.append(response.get("content", ""))

    return "".join(collected).strip() or "No result produced."
