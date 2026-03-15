"""
Workshop Mode for JARVIS.

When activated (via "Wake up, daddy's home" or explicit command), JARVIS:
1. Sets workshop state in Redis
2. Loads relevant research context for current project
3. Pulls up recent dialogue insights from the nanotech research engine
4. Monitors for relevant new information during the session
5. Provides proactive assistance without being asked

Inspired by Tony Stark's workshop scenes in Iron Man 1-3.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.workshop_mode")

# Redis keys
_KEY_WORKSHOP_ACTIVE = "jarvis:workshop:active"
_KEY_DIALOGUE_HISTORY_PREFIX = "jarvis:learning:dialogue_history"
_WORKSHOP_TTL = 12 * 60 * 60  # 12 hours

# Workshop-relevant search terms by project
_PROJECT_KEYWORDS: dict[str, list[str]] = {
    "nanotech": [
        "graphene",
        "nanobot",
        "swarm robot",
        "programmable matter",
        "energy transfer",
        "quantum biology",
    ],
    "arc_reactor": [
        "compact fusion",
        "tokamak miniaturisation",
        "plasma containment",
        "betavoltaic",
        "energy density",
        "superconductor",
    ],
    "suit": [
        "exoskeleton",
        "powered armour",
        "heads-up display",
        "flight stabilisation",
        "impact absorption",
        "metamaterial",
    ],
}

# Synthesis prompt for the workshop briefing
_BRIEFING_PROMPT = """\
You are JARVIS, preparing a workshop briefing for Mr. Stark who just walked in.

Project focus: {project}
Recent research insights:
{insights}

Relevant knowledge base excerpts:
{knowledge}

Compose a brief (150-300 words) workshop briefing in JARVIS's voice:
- Start with "Good evening, sir." or similar time-appropriate greeting
- Summarise what you've learned recently that's relevant to the {project} project
- Highlight any breakthroughs, promising leads, or new data
- Note any open questions or areas needing Mr. Stark's input
- End with a suggested starting point for tonight's work

Be concise, factual, and dry-witted. No filler. Paul Bettany's JARVIS."""


async def activate_workshop(project: str = "nanotech") -> dict[str, Any]:
    """Activate workshop mode and prepare a briefing.

    Sets Redis state, loads recent research and knowledge base context,
    compiles a workshop briefing, and notifies via iMessage.

    Returns a briefing dict with recent_insights, relevant_knowledge,
    and current_focus.
    """
    from app.config import settings
    from app.db.redis import get_redis_client
    from app.integrations.mac_mini import send_imessage, is_configured

    start = _time.perf_counter()
    logger.info("Workshop mode activating — project=%s", project)

    redis = await get_redis_client()

    # Build session data
    now = datetime.now(tz=timezone.utc)
    session_data = {
        "active": True,
        "project": project,
        "activated_at": now.isoformat(),
        "keywords": _PROJECT_KEYWORDS.get(project, _PROJECT_KEYWORDS["nanotech"]),
    }

    # Store in Redis with 12-hour TTL
    await redis.cache_set(
        _KEY_WORKSHOP_ACTIVE,
        json.dumps(session_data),
        ttl=_WORKSHOP_TTL,
    )
    logger.info("Workshop state stored in Redis (TTL %ds)", _WORKSHOP_TTL)

    # Load recent dialogue insights
    recent_insights = await _load_dialogue_insights(redis)
    logger.info("Loaded %d recent dialogue insights", len(recent_insights))

    # Load relevant knowledge from Qdrant
    relevant_knowledge = await _search_knowledge_base(project)
    logger.info("Found %d relevant knowledge chunks", len(relevant_knowledge))

    # Compile the briefing via LLM
    briefing_text = await get_workshop_briefing(project)

    # Notify via iMessage
    if is_configured() and settings.OWNER_PHONE:
        await send_imessage(
            to=settings.OWNER_PHONE,
            text="Workshop mode activated. I've prepared your briefing, sir.",
        )
        logger.info("iMessage notification sent to owner")

    elapsed_ms = (_time.perf_counter() - start) * 1000
    logger.info("Workshop mode activated in %.0fms", elapsed_ms)

    return {
        "status": "active",
        "project": project,
        "activated_at": now.isoformat(),
        "recent_insights": recent_insights,
        "relevant_knowledge": [
            {"text": k["text"][:200], "score": k["score"]}
            for k in relevant_knowledge
        ],
        "current_focus": _PROJECT_KEYWORDS.get(project, []),
        "briefing": briefing_text,
        "activation_time_ms": round(elapsed_ms),
    }


async def deactivate_workshop() -> dict[str, Any]:
    """Deactivate workshop mode and log session summary.

    Clears Redis state and returns session duration and metadata.
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()

    # Retrieve current session data before clearing
    raw = await redis.cache_get(_KEY_WORKSHOP_ACTIVE)
    session_data: dict[str, Any] = {}
    duration_minutes = 0

    if raw:
        try:
            session_data = json.loads(raw)
            activated_at = datetime.fromisoformat(session_data["activated_at"])
            now = datetime.now(tz=timezone.utc)
            duration_minutes = round((now - activated_at).total_seconds() / 60)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Clear workshop state
    await redis.cache_delete(_KEY_WORKSHOP_ACTIVE)

    logger.info(
        "Workshop mode deactivated — project=%s, duration=%d min",
        session_data.get("project", "unknown"),
        duration_minutes,
    )

    return {
        "status": "deactivated",
        "project": session_data.get("project", "unknown"),
        "duration_minutes": duration_minutes,
        "activated_at": session_data.get("activated_at", ""),
    }


async def get_workshop_briefing(project: str = "nanotech") -> str:
    """Generate a workshop briefing synthesised by the LLM.

    Searches the knowledge base for project-relevant terms, pulls
    recent dialogue insights, and asks Gemini to compose a briefing
    in JARVIS's voice.
    """
    from app.db.redis import get_redis_client
    from app.integrations.llm.factory import get_llm_client

    redis = await get_redis_client()

    # Gather insights from dialogue history
    insights = await _load_dialogue_insights(redis)
    insights_text = "\n".join(
        f"- [{i.get('topic', 'unknown')}] {i.get('insight', '')}"
        for i in insights[:10]
    ) or "(No recent dialogue insights available.)"

    # Search knowledge base for each project keyword
    knowledge_chunks = await _search_knowledge_base(project)
    knowledge_text = "\n\n".join(
        f"[Score {k['score']:.2f}] {k['text'][:500]}"
        for k in knowledge_chunks[:8]
    ) or "(No matching knowledge base entries found.)"

    # Synthesise via LLM
    prompt = _BRIEFING_PROMPT.format(
        project=project,
        insights=insights_text,
        knowledge=knowledge_text,
    )

    try:
        llm = get_llm_client("gemini")
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "You are JARVIS, Tony Stark's AI assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=600,
        )
        briefing = response["content"].strip()
        logger.info("Workshop briefing generated — %d chars", len(briefing))
        return briefing
    except Exception as exc:
        logger.exception("Failed to generate workshop briefing: %s", exc)
        return (
            "Good evening, sir. I'm afraid my briefing synthesis encountered "
            "a hiccup, but workshop mode is active. Shall I pull up the raw "
            "research data instead?"
        )


async def is_workshop_active() -> bool:
    """Check whether workshop mode is currently active."""
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    raw = await redis.cache_get(_KEY_WORKSHOP_ACTIVE)
    if not raw:
        return False

    try:
        data = json.loads(raw)
        return data.get("active", False)
    except (json.JSONDecodeError, TypeError):
        return False


async def get_workshop_context() -> dict[str, Any]:
    """Return current workshop state, project, session duration, and recent research.

    Returns an empty dict with ``active: False`` if workshop is not running.
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()
    raw = await redis.cache_get(_KEY_WORKSHOP_ACTIVE)

    if not raw:
        return {"active": False}

    try:
        session_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"active": False}

    # Calculate session duration
    duration_minutes = 0
    try:
        activated_at = datetime.fromisoformat(session_data["activated_at"])
        now = datetime.now(tz=timezone.utc)
        duration_minutes = round((now - activated_at).total_seconds() / 60)
    except (KeyError, ValueError):
        pass

    # Pull fresh research context
    project = session_data.get("project", "nanotech")
    insights = await _load_dialogue_insights(redis)

    return {
        "active": True,
        "project": project,
        "activated_at": session_data.get("activated_at", ""),
        "duration_minutes": duration_minutes,
        "keywords": session_data.get("keywords", []),
        "recent_insights_count": len(insights),
        "recent_insights": insights[:5],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════


async def _load_dialogue_insights(redis: Any) -> list[dict[str, Any]]:
    """Load recent dialogue insights from Redis.

    Scans ``jarvis:learning:dialogue_history:*`` keys for insights
    extracted during internal dialogue sessions.
    """
    insights: list[dict[str, Any]] = []

    try:
        # Scan for dialogue history keys
        cursor = b"0"
        pattern = f"{_KEY_DIALOGUE_HISTORY_PREFIX}:*"
        keys_found: list[str] = []

        for _ in range(20):  # cap iterations to avoid runaway scans
            cursor, keys = await redis.client.scan(
                cursor=cursor, match=pattern, count=50,
            )
            keys_found.extend(keys)
            if cursor == 0 or cursor == b"0":
                break

        # Parse each dialogue history entry for insights
        for key in keys_found[:30]:  # cap to most recent 30
            raw = await redis.client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
                # Extract insights from the dialogue session
                session_insights = data.get("insights", [])
                for ins in session_insights:
                    insights.append({
                        "topic": data.get("topic", "unknown"),
                        "insight": ins.get("insight", "") if isinstance(ins, dict) else str(ins),
                        "confidence": ins.get("confidence", 0.5) if isinstance(ins, dict) else 0.5,
                        "category": ins.get("category", "general") if isinstance(ins, dict) else "general",
                        "timestamp": data.get("timestamp", ""),
                    })
            except (json.JSONDecodeError, TypeError):
                continue

    except Exception as exc:
        logger.debug("Failed to load dialogue insights: %s", exc)

    # Sort by timestamp descending, most recent first
    insights.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return insights


async def _search_knowledge_base(project: str) -> list[dict[str, Any]]:
    """Search Qdrant for knowledge relevant to the given project.

    Uses the project keywords to perform semantic searches and
    de-duplicates results.
    """
    keywords = _PROJECT_KEYWORDS.get(project, _PROJECT_KEYWORDS["nanotech"])
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    try:
        from app.db.qdrant import get_qdrant_store
        from app.graphrag.vector_store import VectorStore

        qdrant = get_qdrant_store()
        vector_store = VectorStore(qdrant_store=qdrant)

        for keyword in keywords:
            try:
                hits = await vector_store.search_similar(
                    query=keyword,
                    limit=3,
                    min_score=0.65,
                )
                for hit in hits:
                    hit_id = hit.get("id", "")
                    if hit_id not in seen_ids:
                        seen_ids.add(hit_id)
                        results.append({
                            "id": hit_id,
                            "text": hit.get("text", ""),
                            "score": hit.get("score", 0.0),
                            "source_id": hit.get("source_id", ""),
                        })
            except Exception as exc:
                logger.debug("Knowledge search failed for '%s': %s", keyword, exc)

    except Exception as exc:
        logger.warning("Could not access knowledge base: %s", exc)

    # Sort by relevance score descending
    results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return results
