"""
Continuous research/learning daemon for J.A.R.V.I.S.

Periodically researches topics Mr. Stark cares about, summarises findings
via Gemini, and stores them in Redis with 7-day TTL.  One topic per cycle,
rotating through the list.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.research_daemon")

# ═══════════════════════════════════════════════════════════════════════════
# Research topics — one is picked per cycle in round-robin order
# ═══════════════════════════════════════════════════════════════════════════

RESEARCH_TOPICS: list[dict[str, Any]] = [
    {
        "name": "business_ideas",
        "label": "Business & Entrepreneurship",
        "queries": [
            "innovative startup ideas 2026",
            "emerging business opportunities technology",
            "solo founder bootstrapped startup trends",
        ],
    },
    {
        "name": "tech_industry",
        "label": "Tech Industry News",
        "queries": [
            "Apple Google AI startup news today",
            "tech industry layoffs funding 2026",
            "Silicon Valley trends this week",
        ],
    },
    {
        "name": "apple_tech",
        "label": "Apple Ecosystem",
        "queries": [
            "Apple news today",
            "SwiftUI new features 2026",
            "iOS macOS developer trends",
            "Xcode updates Swift language",
        ],
    },
    {
        "name": "iron_man_tech",
        "label": "Iron Man / Marvel Tech",
        "queries": [
            "real life iron man technology",
            "powered exoskeleton developments 2026",
            "arc reactor fusion energy research",
            "heads-up display HUD technology",
        ],
    },
    {
        "name": "graphene_nanotech",
        "label": "Graphene & Nanotechnology",
        "queries": [
            "graphene applications breakthroughs 2026",
            "nanotechnology medical industrial advances",
            "carbon nanotube manufacturing progress",
        ],
    },
    {
        "name": "physics",
        "label": "Physics & Materials Science",
        "queries": [
            "quantum computing breakthroughs 2026",
            "materials science discoveries new materials",
            "fusion energy progress latest",
        ],
    },
    {
        "name": "ai_ml",
        "label": "AI / ML Developments",
        "queries": [
            "artificial intelligence developments today",
            "machine learning breakthroughs 2026",
            "large language model open source news",
        ],
    },
    {
        "name": "cybersecurity",
        "label": "Cybersecurity",
        "queries": [
            "cybersecurity threats vulnerabilities 2026",
            "zero-day exploits recent security news",
            "encryption privacy technology advances",
        ],
    },
    {
        "name": "space_tech",
        "label": "Space Technology",
        "queries": [
            "SpaceX NASA space missions 2026",
            "satellite technology orbital launch news",
            "Mars colonisation space exploration progress",
        ],
    },
]

# Redis key constants
_KEY_TOPIC_INDEX = "jarvis:research:last_topic_index"
_KEY_FINDINGS_PREFIX = "jarvis:research:findings"
_KEY_LATEST_PREFIX = "jarvis:research:latest"
_KEY_LAST_RUN = "jarvis:research:last_run"

_SEVEN_DAYS = 7 * 24 * 60 * 60  # 604 800 seconds

# ═══════════════════════════════════════════════════════════════════════════
# Summarisation prompt
# ═══════════════════════════════════════════════════════════════════════════

_SUMMARISE_PROMPT = """\
You are JARVIS, compiling a concise research note for Mr. Stark.

Topic: {topic_label}
Search query: {query}
Raw search results:
{raw_results}

Write a research brief (200-400 words) that:
- Highlights the most important/interesting findings
- Notes any breakthroughs, new products, or notable developments
- Mentions specific names, companies, dates when relevant
- Is factual and informative — no filler
- Ends with a one-line "Bottom line" takeaway

Write ONLY the research note, no preamble."""

# ═══════════════════════════════════════════════════════════════════════════
# Core functions
# ═══════════════════════════════════════════════════════════════════════════


async def run_research_cycle() -> dict[str, Any]:
    """Execute one research cycle.

    Picks the next topic in rotation, runs web searches for each query,
    summarises via Gemini, and stores in Redis.

    Returns a dict with cycle metadata.
    """
    from app.agents.tools import get_tool_registry
    from app.db.redis import get_redis_client
    from app.integrations.llm.factory import get_llm_client

    cycle_start = _time.perf_counter()
    logger.info("═══════════════════════════════════════════════════════")
    logger.info("RESEARCH DAEMON: cycle starting")
    logger.info("═══════════════════════════════════════════════════════")

    redis = await get_redis_client()
    registry = get_tool_registry()
    llm = get_llm_client("gemini")

    # ── Pick next topic ───────────────────────────────────────────────
    raw_index = await redis.cache_get(_KEY_TOPIC_INDEX)
    last_index = int(raw_index) if raw_index else -1
    current_index = (last_index + 1) % len(RESEARCH_TOPICS)
    topic = RESEARCH_TOPICS[current_index]

    logger.info(
        "Topic selected: [%d/%d] %s — \"%s\"",
        current_index + 1, len(RESEARCH_TOPICS),
        topic["name"], topic["label"],
    )
    logger.info("Queries to execute: %s", topic["queries"])

    # Persist index (very long TTL so it survives restarts)
    await redis.cache_set(_KEY_TOPIC_INDEX, str(current_index), ttl=_SEVEN_DAYS * 52)

    # ── Web searches ──────────────────────────────────────────────────
    search_tool = registry.get("web_search")
    if not search_tool:
        msg = "WebSearchTool not found in registry"
        logger.error(msg)
        return {"status": "error", "error": msg}

    raw_results_parts: list[str] = []
    successful_queries = 0

    for i, query in enumerate(topic["queries"], 1):
        q_start = _time.perf_counter()
        try:
            result = await search_tool.run({"query": query, "max_results": 4})
            q_ms = (_time.perf_counter() - q_start) * 1000
            result_len = len(result) if result else 0
            has_results = result_len > 50 and "unavailable" not in result.lower()

            if has_results:
                successful_queries += 1
                logger.info(
                    "  Search [%d/%d] OK — query=\"%s\" — %d chars in %.0fms",
                    i, len(topic["queries"]), query, result_len, q_ms,
                )
                # Log first 150 chars of results for debugging
                logger.info("    Preview: %s", result[:150].replace("\n", " "))
            else:
                logger.warning(
                    "  Search [%d/%d] EMPTY — query=\"%s\" — len=%d, %.0fms",
                    i, len(topic["queries"]), query, result_len, q_ms,
                )
                if result:
                    logger.warning("    Response: %s", result[:100].replace("\n", " "))

            raw_results_parts.append(f"### Query: {query}\n{result}")
        except Exception as exc:
            q_ms = (_time.perf_counter() - q_start) * 1000
            logger.error(
                "  Search [%d/%d] FAILED — query=\"%s\" — %.0fms — %r",
                i, len(topic["queries"]), query, q_ms, exc,
            )
            raw_results_parts.append(f"### Query: {query}\n(search failed: {exc})")

    combined_raw = "\n\n".join(raw_results_parts)
    logger.info(
        "Search phase complete: %d/%d queries successful, combined_raw=%d chars",
        successful_queries, len(topic["queries"]), len(combined_raw),
    )

    if not any("search results" in p.lower() for p in raw_results_parts):
        logger.warning(
            "ALL searches returned no useful results for topic=%s — "
            "storing placeholder note",
            topic["name"],
        )
        combined_raw = "(All web searches returned limited results this cycle.)"

    # ── Summarise via Gemini ──────────────────────────────────────────
    prompt = _SUMMARISE_PROMPT.format(
        topic_label=topic["label"],
        query=", ".join(topic["queries"]),
        raw_results=combined_raw[:8000],  # cap input length
    )

    logger.info(
        "Sending to Gemini for summarisation — prompt=%d chars (raw capped at 8000)",
        len(prompt),
    )
    llm_start = _time.perf_counter()

    try:
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "You are JARVIS, a research assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=800,
        )
        summary = response["content"].strip()
        llm_ms = (_time.perf_counter() - llm_start) * 1000
        logger.info(
            "Gemini summarisation complete — %d chars in %.0fms",
            len(summary), llm_ms,
        )
        logger.info("Summary preview: %.200s", summary.replace("\n", " "))
    except Exception as exc:
        llm_ms = (_time.perf_counter() - llm_start) * 1000
        logger.error(
            "LLM summarisation FAILED after %.0fms: %r", llm_ms, exc,
        )
        summary = f"Research summary unavailable — LLM error: {exc}"

    # ── Store in Redis ────────────────────────────────────────────────
    now = datetime.now(tz=timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    finding = {
        "topic": topic["name"],
        "label": topic["label"],
        "date": date_str,
        "timestamp": now.isoformat(),
        "queries": topic["queries"],
        "summary": summary,
    }
    finding_json = json.dumps(finding)
    finding_bytes = len(finding_json.encode())

    # Dated key with 7-day TTL
    dated_key = f"{_KEY_FINDINGS_PREFIX}:{topic['name']}:{date_str}"
    await redis.cache_set(dated_key, finding_json, ttl=_SEVEN_DAYS)
    logger.info("Redis SET %s — %d bytes (TTL 7d)", dated_key, finding_bytes)

    # "Latest" key per topic (overwritten each cycle, 14-day TTL)
    latest_key = f"{_KEY_LATEST_PREFIX}:{topic['name']}"
    await redis.cache_set(latest_key, finding_json, ttl=_SEVEN_DAYS * 2)
    logger.info("Redis SET %s — %d bytes (TTL 14d)", latest_key, finding_bytes)

    # Last-run timestamp
    await redis.cache_set(_KEY_LAST_RUN, now.isoformat(), ttl=_SEVEN_DAYS * 52)
    logger.info("Redis SET %s = %s", _KEY_LAST_RUN, now.isoformat())

    total_s = (_time.perf_counter() - cycle_start)
    logger.info("═══════════════════════════════════════════════════════")
    logger.info(
        "RESEARCH DAEMON: cycle complete — topic=%s, "
        "queries=%d/%d ok, summary=%d chars, total=%.1fs",
        topic["name"], successful_queries, len(topic["queries"]),
        len(summary), total_s,
    )
    logger.info("═══════════════════════════════════════════════════════")

    return {
        "status": "ok",
        "topic": topic["name"],
        "label": topic["label"],
        "date": date_str,
        "summary_length": len(summary),
        "queries_run": len(topic["queries"]),
        "queries_successful": successful_queries,
        "total_time_ms": round(total_s * 1000),
        "summary_preview": summary[:200],
    }


async def get_research_summary(
    topic: str = "",
    days: int = 3,
) -> str:
    """Return recent research findings as a formatted string.

    Parameters
    ----------
    topic : str
        Filter to a specific topic name.  Empty string returns all topics.
    days : int
        How many days back to include (default 3).

    Returns a human-readable summary suitable for JARVIS to relay.
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    sections: list[str] = []

    topics_to_check = (
        [t for t in RESEARCH_TOPICS if t["name"] == topic]
        if topic
        else RESEARCH_TOPICS
    )

    if topic and not topics_to_check:
        return f"Unknown research topic: '{topic}'. Available: {', '.join(t['name'] for t in RESEARCH_TOPICS)}"

    for t in topics_to_check:
        # Try latest key first
        latest_key = f"{_KEY_LATEST_PREFIX}:{t['name']}"
        raw = await redis.cache_get(latest_key)
        if raw:
            try:
                finding = json.loads(raw)
                # Check age
                finding_date = datetime.fromisoformat(finding["timestamp"])
                age_days = (datetime.now(tz=timezone.utc) - finding_date).days
                if age_days <= days:
                    sections.append(
                        f"## {finding['label']} ({finding['date']})\n{finding['summary']}"
                    )
            except (json.JSONDecodeError, KeyError) as exc:
                logger.debug("Failed to parse finding for %s: %s", t["name"], exc)

    if not sections:
        last_run = await redis.cache_get(_KEY_LAST_RUN)
        if last_run:
            return (
                f"No research findings in the last {days} day(s). "
                f"Last research cycle ran at {last_run}. "
                "Try increasing the days parameter or running a new cycle."
            )
        return "No research findings yet. The research daemon hasn't run any cycles."

    header = f"# JARVIS Research Briefing ({len(sections)} topic{'s' if len(sections) != 1 else ''})\n"
    return header + "\n\n".join(sections)


async def get_all_topic_names() -> list[dict[str, str]]:
    """Return list of available research topics with name and label."""
    return [{"name": t["name"], "label": t["label"]} for t in RESEARCH_TOPICS]
