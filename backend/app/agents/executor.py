"""
Executor agent node for the J.A.R.V.I.S. orchestrator.

Parses the planned tool calls from the planner output and executes
them -- either sequentially or in parallel -- via the unified tool
registry defined in ``app.agents.tools``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.agents.state import AgentState

logger = logging.getLogger("jarvis.agents.executor")

# Maximum number of tools that may run concurrently
_MAX_PARALLEL = 5

# Hard timeout per tool invocation (seconds)
_TOOL_TIMEOUT = 30.0


async def executor_node(state: AgentState) -> dict[str, Any]:
    """Execute the tool calls specified in the current plan.

    Returns a partial state update with ``tool_results`` -- a list of
    dicts, one per tool call, each containing ``tool``, ``params``,
    ``result``, ``status``, and ``duration_ms``.
    """
    from app.agents.tools import get_tool_registry

    # 1. Parse planned tool calls ------------------------------------------
    plan: dict[str, Any] = {}
    try:
        plan = json.loads(state.get("current_plan", "{}"))
    except json.JSONDecodeError:
        pass

    planned_calls: list[dict[str, Any]] = plan.get("tool_calls", [])
    if not planned_calls:
        logger.info("Executor invoked but no tool_calls in plan; skipping.")
        return {"tool_results": []}

    registry = get_tool_registry()

    # 2. Execute calls (parallel where possible) ---------------------------
    semaphore = asyncio.Semaphore(_MAX_PARALLEL)

    async def _run_one(call: dict[str, Any]) -> dict[str, Any]:
        tool_name = call.get("tool", "")
        params = call.get("params", {})
        start = time.monotonic()

        tool = registry.get(tool_name)
        if tool is None:
            return {
                "tool": tool_name,
                "params": params,
                "result": f"Unknown tool: {tool_name}",
                "status": "error",
                "duration_ms": 0.0,
            }

        async with semaphore:
            try:
                result = await asyncio.wait_for(
                    tool.run(params, state=state),
                    timeout=_TOOL_TIMEOUT,
                )
                elapsed = (time.monotonic() - start) * 1000
                return {
                    "tool": tool_name,
                    "params": params,
                    "result": result,
                    "status": "success",
                    "duration_ms": round(elapsed, 2),
                }
            except asyncio.TimeoutError:
                elapsed = (time.monotonic() - start) * 1000
                logger.warning("Tool '%s' timed out after %.0f ms", tool_name, elapsed)
                return {
                    "tool": tool_name,
                    "params": params,
                    "result": f"Tool timed out after {_TOOL_TIMEOUT}s.",
                    "status": "timeout",
                    "duration_ms": round(elapsed, 2),
                }
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                logger.exception("Tool '%s' failed: %s", tool_name, exc)
                return {
                    "tool": tool_name,
                    "params": params,
                    "result": f"Tool error: {exc}",
                    "status": "error",
                    "duration_ms": round(elapsed, 2),
                }

    tasks = [_run_one(call) for call in planned_calls]
    results = await asyncio.gather(*tasks)
    tool_results = list(results)

    logger.info(
        "Executor completed %d tool calls (%d succeeded).",
        len(tool_results),
        sum(1 for r in tool_results if r["status"] == "success"),
    )

    return {"tool_results": tool_results}
