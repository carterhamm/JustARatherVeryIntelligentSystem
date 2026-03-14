"""
Internal dialogue system for JARVIS continuous learning.

Runs a multi-round debate between two LLM personas on a given topic:
  - JARVIS (analytical, British, slightly opinionated)
  - ANALYST (neutral, rigorous, contrarian)

The dialogue surfaces deeper insights than single-pass summarization.
Key findings are extracted and stored in the knowledge base.

Part of Phase 2: Continuous Learning (Days 3-5).
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.internal_dialogue")

# Redis keys
_KEY_DIALOGUE_HISTORY = "jarvis:learning:dialogue_history"
_KEY_DIALOGUE_COUNT = "jarvis:learning:dialogue_count"
_DIALOGUE_HISTORY_TTL = 86400 * 14  # 14 days

_JARVIS_SYSTEM = """\
You are JARVIS — an advanced AI system with dry British wit and deep technical knowledge.
You are engaged in an analytical discussion about a research topic. Your role:
- Draw connections between the topic and practical applications
- Reference relevant technologies, companies, or research teams
- Consider implications for AI, nanotechnology, energy, or space exploration
- Be opinionated but grounded in evidence
- Keep responses concise (2-4 paragraphs)
- Occasionally reference how Mr. Stark (your creator) might find this useful"""

_ANALYST_SYSTEM = """\
You are a neutral research analyst. You are engaged in a critical discussion about a research topic. Your role:
- Challenge assumptions and identify weaknesses in arguments
- Raise counterpoints and alternative interpretations
- Highlight risks, limitations, or overlooked factors
- Cite specific data points or studies when possible
- Maintain objectivity — no enthusiasm or bias
- Keep responses concise (2-4 paragraphs)
- Push for deeper analysis beyond surface-level observations"""

_INSIGHT_EXTRACTION_PROMPT = """\
Analyse this dialogue between JARVIS and an analyst about "{topic}".

Extract the most valuable insights — things that go beyond the original research summary.
Focus on:
1. Novel connections or applications identified
2. Critical risks or limitations raised
3. Actionable opportunities mentioned
4. Surprising or non-obvious conclusions
5. Key disagreements and their resolution

Output a JSON array of insight objects:
[
  {{
    "insight": "one-sentence key insight",
    "category": "application|risk|opportunity|connection|prediction",
    "confidence": 0.0-1.0,
    "source_turn": <which turn number contributed most>
  }}
]

Output ONLY valid JSON. No markdown, no commentary.

Dialogue:
{dialogue}"""


async def run_dialogue_session(
    topic: str,
    summary: str,
    rounds: int = 3,
    use_local_llm: bool = False,
) -> dict[str, Any]:
    """Run a multi-round dialogue between JARVIS and ANALYST on a topic.

    Parameters
    ----------
    topic : str
        The topic label (e.g. "Quantum Computing Breakthrough")
    summary : str
        The research summary to discuss
    rounds : int
        Number of dialogue rounds (default 3)
    use_local_llm : bool
        If True, use Stark Protocol (local Gemma) for ANALYST.
        Falls back to Gemini if Stark Protocol unavailable.

    Returns
    -------
    dict with:
        - topic: str
        - rounds: int
        - dialogue: list of turns
        - insights: list of extracted insights
        - total_time_ms: int
    """
    from app.integrations.llm.factory import get_llm_client

    start = _time.perf_counter()

    # Primary LLM for JARVIS (always Gemini)
    jarvis_llm = get_llm_client("gemini")

    # Secondary LLM for ANALYST — try local Gemma first
    analyst_llm = jarvis_llm  # default fallback
    if use_local_llm:
        try:
            from app.config import settings
            if settings.STARK_PROTOCOL_ENABLED and settings.STARK_PROTOCOL_URL:
                analyst_llm = get_llm_client("stark_protocol")
                logger.info("ANALYST using Stark Protocol (local Gemma)")
        except Exception:
            logger.debug("Stark Protocol unavailable, ANALYST using Gemini")

    dialogue: list[dict[str, str]] = []

    # Opening message from JARVIS
    jarvis_history = [
        {"role": "system", "content": _JARVIS_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Let's discuss this research finding about {topic}.\n\n"
                f"Summary:\n{summary}\n\n"
                "What are the most significant implications here? "
                "What connections do you see to broader technological trends?"
            ),
        },
    ]

    for round_num in range(1, rounds + 1):
        # JARVIS speaks
        try:
            jarvis_resp = await jarvis_llm.chat_completion(
                messages=jarvis_history,
                temperature=0.7,
                max_tokens=500,
            )
            jarvis_text = jarvis_resp["content"].strip()
        except Exception as exc:
            logger.warning("JARVIS dialogue turn %d failed: %s", round_num, exc)
            jarvis_text = f"[JARVIS turn {round_num} failed: {exc}]"

        dialogue.append({
            "speaker": "JARVIS",
            "round": round_num,
            "text": jarvis_text,
        })

        # Update JARVIS history
        jarvis_history.append({"role": "assistant", "content": jarvis_text})

        # ANALYST responds
        analyst_messages = [
            {"role": "system", "content": _ANALYST_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Topic: {topic}\n\n"
                    f"Original summary:\n{summary}\n\n"
                    f"JARVIS's analysis:\n{jarvis_text}\n\n"
                    "Provide a critical counterpoint. Challenge the assumptions, "
                    "identify risks, and push for deeper analysis."
                ),
            },
        ]

        try:
            analyst_resp = await analyst_llm.chat_completion(
                messages=analyst_messages,
                temperature=0.5,
                max_tokens=500,
            )
            analyst_text = analyst_resp["content"].strip()
        except Exception as exc:
            logger.warning("ANALYST dialogue turn %d failed: %s", round_num, exc)
            analyst_text = f"[ANALYST turn {round_num} failed: {exc}]"

        dialogue.append({
            "speaker": "ANALYST",
            "round": round_num,
            "text": analyst_text,
        })

        # Feed ANALYST's response back to JARVIS for next round
        jarvis_history.append({
            "role": "user",
            "content": f"The analyst responds:\n{analyst_text}\n\nRespond to their points.",
        })

    # Extract insights from the dialogue
    insights = await _extract_insights(topic, dialogue, jarvis_llm)

    elapsed_ms = int((_time.perf_counter() - start) * 1000)

    result = {
        "topic": topic,
        "rounds": rounds,
        "dialogue": dialogue,
        "insights": insights,
        "total_time_ms": elapsed_ms,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    # Cache the dialogue in Redis
    await _store_dialogue(result)

    logger.info(
        "Dialogue session complete: topic='%s', %d rounds, %d insights, %dms",
        topic, rounds, len(insights), elapsed_ms,
    )

    return result


async def _extract_insights(
    topic: str,
    dialogue: list[dict[str, str]],
    llm: Any,
) -> list[dict[str, Any]]:
    """Use LLM to extract key insights from the dialogue."""
    dialogue_text = "\n\n".join(
        f"**{turn['speaker']}** (Round {turn['round']}):\n{turn['text']}"
        for turn in dialogue
    )

    prompt = _INSIGHT_EXTRACTION_PROMPT.format(
        topic=topic,
        dialogue=dialogue_text[:6000],
    )

    try:
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "Extract structured insights from dialogues. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
        )

        raw = response["content"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        insights = json.loads(raw)
        if not isinstance(insights, list):
            insights = insights.get("insights", []) if isinstance(insights, dict) else []

        # Validate
        validated = []
        for ins in insights:
            if isinstance(ins, dict) and ins.get("insight"):
                validated.append({
                    "insight": ins["insight"],
                    "category": ins.get("category", "connection"),
                    "confidence": min(1.0, max(0.0, float(ins.get("confidence", 0.7)))),
                    "source_turn": ins.get("source_turn", 1),
                })

        return validated

    except Exception as exc:
        logger.warning("Insight extraction failed: %s", exc)
        return []


async def _store_dialogue(result: dict[str, Any]) -> None:
    """Store dialogue result in Redis history."""
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()

        # Store individual dialogue
        key = f"{_KEY_DIALOGUE_HISTORY}:{result['topic']}:{result['timestamp'][:10]}"
        await redis.cache_set(key, json.dumps(result), ttl=_DIALOGUE_HISTORY_TTL)

        # Increment dialogue count
        count_raw = await redis.cache_get(_KEY_DIALOGUE_COUNT)
        count = int(count_raw) if count_raw else 0
        await redis.cache_set(
            _KEY_DIALOGUE_COUNT, str(count + 1), ttl=86400 * 365,
        )
    except Exception:
        logger.debug("Failed to store dialogue in Redis", exc_info=True)


async def get_dialogue_history(days: int = 7) -> list[dict[str, Any]]:
    """Return recent dialogue session results from Redis."""
    from app.db.redis import get_redis_client
    from datetime import timedelta

    try:
        redis = await get_redis_client()
        results: list[dict[str, Any]] = []

        # Scan for dialogue keys
        now = datetime.now(tz=timezone.utc)
        for day_offset in range(days):
            date_str = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            # We can't scan Redis keys with this client, so we check known topic patterns
            from app.services.research_daemon import RESEARCH_TOPICS
            for topic in RESEARCH_TOPICS:
                key = f"{_KEY_DIALOGUE_HISTORY}:{topic['name']}:{date_str}"
                raw = await redis.cache_get(key)
                if raw:
                    try:
                        results.append(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass

        return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception:
        logger.debug("Failed to retrieve dialogue history", exc_info=True)
        return []
