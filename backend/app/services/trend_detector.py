"""
Dynamic trend detection for JARVIS continuous learning.

Discovers trending topics in tech, science, and business via web search,
then scores them by relevance to Mr. Stark's interests.  Supplements
the fixed 9-topic rotation with dynamically discovered topics.

Part of Phase 2: Continuous Learning (Days 3-5).
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("jarvis.trend_detector")

# Mr. Stark's interest domains — used for relevance scoring
_INTEREST_DOMAINS = [
    "artificial intelligence", "machine learning", "LLM",
    "Apple", "iOS", "Swift", "macOS", "iPhone",
    "startup", "entrepreneurship", "SaaS", "bootstrap",
    "nanotechnology", "graphene", "carbon nanotubes",
    "fusion energy", "arc reactor", "clean energy",
    "exoskeleton", "powered suit", "HUD", "augmented reality",
    "quantum computing", "quantum physics",
    "space", "SpaceX", "NASA", "Mars",
    "cybersecurity", "encryption", "zero-day",
    "BYU", "Cougars",
    "Iron Man", "Marvel", "Tony Stark",
    "robotics", "automation", "home automation",
]

# Trend discovery queries — rotated to avoid repetition
_TREND_QUERIES = [
    "trending technology news today",
    "biggest science breakthroughs this week",
    "trending AI and machine learning developments",
    "trending startup and business news today",
    "trending Apple and tech industry news",
    "trending space and physics discoveries",
    "trending cybersecurity news today",
    "latest nanotechnology and materials science breakthroughs",
    "trending engineering and robotics innovations",
]

# Redis keys
_KEY_TREND_CACHE = "jarvis:learning:trends"
_KEY_TREND_INDEX = "jarvis:learning:trend_query_index"
_TREND_CACHE_TTL = 3600  # 1 hour


async def detect_trending_topics(max_topics: int = 5) -> list[dict[str, Any]]:
    """Discover trending topics via web search and LLM extraction.

    Returns a list of topic dicts:
        - name: short topic identifier
        - label: human-readable label
        - description: why it's trending
        - relevance_score: 0-10 relevance to Mr. Stark's interests
        - queries: suggested search queries for deeper research
        - source: "trending"
    """
    from app.agents.tools import get_tool_registry
    from app.db.redis import get_redis_client
    from app.integrations.llm.factory import get_llm_client

    redis = await get_redis_client()

    # Check cache first
    cached = await redis.cache_get(_KEY_TREND_CACHE)
    if cached:
        try:
            topics = json.loads(cached)
            logger.debug("Returning %d cached trending topics", len(topics))
            return topics[:max_topics]
        except (json.JSONDecodeError, TypeError):
            pass

    start = _time.perf_counter()

    # Pick next trend query (round-robin)
    raw_index = await redis.cache_get(_KEY_TREND_INDEX)
    query_index = int(raw_index) if raw_index else 0
    queries_to_run = [
        _TREND_QUERIES[query_index % len(_TREND_QUERIES)],
        _TREND_QUERIES[(query_index + 1) % len(_TREND_QUERIES)],
    ]
    await redis.cache_set(
        _KEY_TREND_INDEX,
        str((query_index + 2) % len(_TREND_QUERIES)),
        ttl=86400 * 365,
    )

    # Run web searches
    registry = get_tool_registry()
    search_tool = registry.get("web_search")
    if not search_tool:
        logger.warning("No web_search tool available for trend detection")
        return []

    combined_results: list[str] = []
    for query in queries_to_run:
        try:
            result = await search_tool.run({"query": query, "max_results": 6})
            if result and len(result) > 50:
                combined_results.append(f"### {query}\n{result}")
        except Exception as exc:
            logger.warning("Trend search failed for '%s': %s", query, exc)

    if not combined_results:
        return []

    # Use LLM to extract structured trending topics
    llm = get_llm_client("gemini")

    extraction_prompt = f"""Analyse these search results and extract the {max_topics} most significant trending topics.

For each topic, provide:
- name: a short snake_case identifier (e.g. "quantum_chip_breakthrough")
- label: human-readable title (e.g. "Google's New Quantum Chip")
- description: one sentence on why it's trending
- relevance_score: 0-10 relevance to these interests: {', '.join(_INTEREST_DOMAINS[:15])}
- queries: list of 2-3 search queries for deeper research on this topic

Prioritise topics that are:
1. Genuinely new/breaking (not evergreen)
2. Relevant to AI, tech, science, startups, or Mr. Stark's interests
3. Impactful or significant developments

Output ONLY valid JSON array. No markdown, no commentary.

Search results:
{chr(10).join(combined_results)[:8000]}"""

    try:
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "You extract structured trending topics from search results. Output ONLY valid JSON."},
                {"role": "user", "content": extraction_prompt},
            ],
            temperature=0.2,
            max_tokens=1200,
        )

        raw = response["content"].strip()
        # Handle markdown fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        topics = json.loads(raw)
        if not isinstance(topics, list):
            topics = topics.get("topics", []) if isinstance(topics, dict) else []

        # Validate and normalise
        validated: list[dict[str, Any]] = []
        for t in topics:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            validated.append({
                "name": t["name"],
                "label": t.get("label", t["name"].replace("_", " ").title()),
                "description": t.get("description", ""),
                "relevance_score": min(10, max(0, int(t.get("relevance_score", 5)))),
                "queries": t.get("queries", [f"{t['label']} latest news"]),
                "source": "trending",
            })

        # Sort by relevance
        validated.sort(key=lambda x: x["relevance_score"], reverse=True)
        validated = validated[:max_topics]

        elapsed_ms = (_time.perf_counter() - start) * 1000
        logger.info(
            "Detected %d trending topics in %.0fms: %s",
            len(validated), elapsed_ms,
            [t["name"] for t in validated],
        )

        # Cache for 1 hour
        await redis.cache_set(
            _KEY_TREND_CACHE,
            json.dumps(validated),
            ttl=_TREND_CACHE_TTL,
        )

        return validated

    except Exception as exc:
        logger.exception("Trend detection failed: %s", exc)
        return []


async def get_personalized_topics(count: int = 3) -> list[dict[str, Any]]:
    """Get a mix of trending topics personalised to Mr. Stark's interests.

    Returns only topics with relevance_score >= 6.
    Falls back to the most relevant trending topics if none score high enough.
    """
    all_topics = await detect_trending_topics(max_topics=count * 2)
    if not all_topics:
        return []

    # Filter by relevance
    relevant = [t for t in all_topics if t.get("relevance_score", 0) >= 6]

    if relevant:
        return relevant[:count]

    # Fall back to top N by score
    return all_topics[:count]


async def get_combined_research_topics(
    fixed_topic: dict[str, Any],
    trending_count: int = 2,
) -> list[dict[str, Any]]:
    """Combine one fixed rotation topic with dynamically discovered trending topics.

    Returns a list of topic dicts ready for the research daemon.
    The fixed topic always comes first.
    """
    topics = [
        {
            "name": fixed_topic["name"],
            "label": fixed_topic["label"],
            "queries": fixed_topic["queries"],
            "source": "rotation",
        }
    ]

    trending = await get_personalized_topics(count=trending_count)
    for t in trending:
        topics.append({
            "name": t["name"],
            "label": t["label"],
            "queries": t.get("queries", [f"{t['label']} latest"]),
            "source": "trending",
        })

    return topics
