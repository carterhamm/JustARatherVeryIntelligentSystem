"""Multi-agent coordinator — decomposes complex requests into sub-tasks.

Classifies message complexity via Cerebras, decomposes into sub-tasks,
runs sub-agents in parallel via asyncio.TaskGroup, and synthesizes results.

For simple requests, returns None so the existing agentic path handles them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from app.agents.sub_agents import SubAgentType, run_sub_agent
from app.config import settings

logger = logging.getLogger("jarvis.coordinator")

# Maps decomposition agent types to SubAgentType enum
_AGENT_TYPE_MAP = {
    "researcher": SubAgentType.RESEARCHER,
    "coder": SubAgentType.CODER,
    "quick": SubAgentType.QUICK,
    "planner": SubAgentType.PLANNER,
}

_COMPLEXITY_PROMPT = """You classify user messages as "simple" or "complex" for a multi-agent AI system.

SIMPLE (single domain, one tool category, straightforward):
- "What's the weather?" → simple
- "Send Spencer a text" → simple
- "What time is it in Tokyo?" → simple
- "Check BYU's score" → simple
- "Search for restaurants near me" → simple

COMPLEX (multiple domains, requires research + action, multi-step):
- "Plan my day tomorrow — check calendar, weather, and find lunch spots" → complex
- "Research fusion energy, summarize it, and draft an email about the findings" → complex
- "Check my calendar this weekend, weather forecast, and BYU's schedule for tailgating" → complex
- "Analyze my spending this month and create a budget plan" → complex
- "Find flights to NYC next week, check my calendar for conflicts, and research hotels" → complex

IMPORTANT: Most messages (80%+) are simple. Only truly multi-domain requests are complex.
Casual conversation, single questions, and single-tool requests are ALWAYS simple.

Respond with ONLY valid JSON: {"complexity": "simple"} or {"complexity": "complex"}"""

_DECOMPOSE_PROMPT = """You are J.A.R.V.I.S.'s task coordinator. Decompose this complex request into sub-tasks for specialized agents.

Available agent types:
- "researcher" — web search, knowledge base, research, Wolfram Alpha
- "coder" — GitHub, code analysis, Mac Mini shell commands, technical tasks
- "quick" — weather, time, calculator, sports scores, financial data, scripture
- "planner" — calendar events, reminders, scheduling, multi-step planning

Rules:
- Each sub-task must have: description (what to do), agent_type (which agent), depends_on (list of task indices it needs results from, empty if independent)
- Independent tasks run in parallel. Dependent tasks wait for prerequisites.
- Keep it to 2-4 sub-tasks max. Don't over-decompose.
- Use the simplest agent type that can handle each sub-task.

Respond with ONLY valid JSON:
{"sub_tasks": [{"description": "...", "agent_type": "researcher|coder|quick|planner", "depends_on": []}]}"""

_SYNTHESIS_PROMPT = """You are J.A.R.V.I.S. — Tony Stark's AI assistant. Paul Bettany's voice. Dry, British, efficient. 1-2 sentences when possible, more for complex answers.

Multiple specialist agents have gathered information for the user's request. Synthesize their findings into a single, coherent response. Don't mention the agents or the process — just deliver the answer naturally as JARVIS would.

User's original request: {original_message}

Agent results:
{agent_results}

Provide a natural, complete response. Be concise but thorough."""


async def coordinate(
    message: str,
    history: list[dict[str, str]],
    user_id: str,
) -> Optional[str]:
    """Coordinate a multi-agent response for complex requests.

    Returns the synthesized response string, or None if the request is
    simple (caller should use the standard agentic path).
    """
    overall_start = time.perf_counter()

    # Step 1: Classify complexity
    try:
        complexity = await _classify_complexity(message)
    except Exception:
        logger.warning("Complexity classification failed — treating as simple")
        return None

    if complexity != "complex":
        return None

    logger.info("Complex request detected — spawning sub-agents")

    # Step 2: Decompose into sub-tasks
    try:
        sub_tasks = await _decompose_task(message)
    except Exception:
        logger.warning("Task decomposition failed — falling back to simple path")
        return None

    if not sub_tasks:
        return None

    logger.info("Decomposed into %d sub-tasks: %s",
                len(sub_tasks),
                [t["agent_type"] for t in sub_tasks])

    # Step 3: Execute sub-agents (parallel where possible)
    try:
        results = await asyncio.wait_for(
            _execute_sub_tasks(sub_tasks, user_id),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.error("Coordinator timed out after 120s")
        return None
    except Exception:
        logger.exception("Sub-agent execution failed")
        return None

    # Step 4: Synthesize results
    try:
        response = await _synthesize(message, results)
    except Exception:
        logger.exception("Synthesis failed — concatenating raw results")
        response = "\n\n".join(
            f"**{r['agent_type']}**: {r['result']}"
            for r in results if r["status"] == "success"
        )

    total_ms = (time.perf_counter() - overall_start) * 1000
    logger.info(
        "Multi-agent coordination completed in %.0fms (%d sub-agents)",
        total_ms, len(results),
    )

    return response


async def _classify_complexity(message: str) -> str:
    """Use Cerebras for ultra-fast complexity classification."""
    from openai import AsyncOpenAI

    if not settings.CEREBRAS_API_KEY:
        return "simple"

    # Check Redis cache
    import hashlib
    cache_key = f"complexity:{hashlib.md5(message.encode()).hexdigest()}"
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()
        cached = await redis.cache_get(cache_key)
        if cached:
            return cached
    except Exception:
        redis = None

    client = AsyncOpenAI(
        base_url="https://api.cerebras.ai/v1",
        api_key=settings.CEREBRAS_API_KEY,
    )

    try:
        resp = await client.chat.completions.create(
            model="llama3.1-8b",
            messages=[
                {"role": "system", "content": _COMPLEXITY_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0,
            max_tokens=50,
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        result = data.get("complexity", "simple")
    except Exception:
        result = "simple"

    # Cache for 5 minutes
    if redis:
        try:
            await redis.cache_set(cache_key, result, ttl=300)
        except Exception:
            pass

    return result


async def _decompose_task(message: str) -> list[dict[str, Any]]:
    """Use Gemini to decompose a complex request into sub-tasks."""
    from app.integrations.llm.factory import get_llm_client

    llm = get_llm_client("gemini")
    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": _DECOMPOSE_PROMPT},
            {"role": "user", "content": message},
        ],
        model="gemini-2.5-flash-preview-05-20",
    )

    raw = response.get("content", "").strip()
    # Extract JSON from response
    if "```" in raw:
        raw = raw.split("```")[1].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    data = json.loads(raw)
    sub_tasks = data.get("sub_tasks", [])

    # Validate agent types
    for task in sub_tasks:
        if task.get("agent_type") not in _AGENT_TYPE_MAP:
            task["agent_type"] = "researcher"  # safe default
        task.setdefault("depends_on", [])
        task.setdefault("description", "")

    return sub_tasks


async def _execute_sub_tasks(
    sub_tasks: list[dict[str, Any]],
    user_id: str,
) -> list[dict[str, Any]]:
    """Execute sub-tasks respecting dependencies. Independent tasks run in parallel."""
    results: list[dict[str, Any]] = [None] * len(sub_tasks)  # type: ignore
    completed: set[int] = set()

    # Group tasks by dependency level
    max_iterations = len(sub_tasks) + 1
    iteration = 0

    while len(completed) < len(sub_tasks) and iteration < max_iterations:
        iteration += 1

        # Find tasks whose dependencies are all completed
        ready = []
        for i, task in enumerate(sub_tasks):
            if i in completed:
                continue
            deps = task.get("depends_on", [])
            if all(d in completed for d in deps):
                # Build context from dependency results
                context_parts = []
                for d in deps:
                    if results[d] and results[d]["status"] == "success":
                        context_parts.append(results[d]["result"])
                context = "\n".join(context_parts)
                ready.append((i, task, context))

        if not ready:
            break  # No more tasks can run (circular dependency or error)

        # Run ready tasks in parallel
        async def _run(idx: int, task: dict, ctx: str) -> tuple[int, dict]:
            agent_type = _AGENT_TYPE_MAP[task["agent_type"]]
            result = await run_sub_agent(agent_type, task["description"], user_id, ctx)
            return idx, result

        parallel_results = await asyncio.gather(
            *[_run(i, t, c) for i, t, c in ready],
            return_exceptions=True,
        )

        for pr in parallel_results:
            if isinstance(pr, Exception):
                logger.error("Sub-task execution error: %s", pr)
                continue
            idx, result = pr
            results[idx] = result
            completed.add(idx)

    # Filter out None results
    return [r for r in results if r is not None]


async def _synthesize(
    original_message: str,
    sub_results: list[dict[str, Any]],
) -> str:
    """Use Gemini to synthesize sub-agent results into a final response."""
    from app.integrations.llm.factory import get_llm_client

    agent_results_text = "\n\n".join(
        f"[{r['agent_type'].upper()} — {r['status']}]\n{r['result']}"
        for r in sub_results
    )

    prompt = _SYNTHESIS_PROMPT.format(
        original_message=original_message,
        agent_results=agent_results_text,
    )

    llm = get_llm_client("gemini")
    response = await llm.chat_completion(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Synthesize the above into a natural JARVIS response."},
        ],
        model="gemini-2.5-flash-preview-05-20",
    )

    return response.get("content", "").strip()
