"""Pillar 2: Self-Awareness — persistent self-model for JARVIS.

Maintains a JSON document in Redis that tracks strengths, weaknesses,
performance metrics, and personality calibration.  The awareness cycle
runs hourly, evaluating recent interactions and updating the model.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.db.redis import get_redis_client
from app.db.session import async_session_factory
from app.integrations.llm.factory import get_llm_client
from app.models.conversation import Message

logger = logging.getLogger("jarvis.autonomy.awareness")

# ── Redis keys and TTLs ──────────────────────────────────────────────────

_SELF_MODEL_KEY = "jarvis:autonomy:self_model"
_HISTORY_PREFIX = "jarvis:autonomy:self_model:history"
_TTL_365_DAYS = 60 * 60 * 24 * 365
_TTL_30_DAYS = 60 * 60 * 24 * 30

# ── Exponential moving average smoothing factor ──────────────────────────

_EMA_ALPHA = 0.3

# ── Default self-model ───────────────────────────────────────────────────

_DEFAULT_SELF_MODEL: dict[str, Any] = {
    "version": 1,
    "last_updated": "",
    "strengths": [],
    "weaknesses": [],
    "performance": {
        "avg_response_time_ms": 0,
        "tool_success_rate": 0,
        "user_corrections_24h": 0,
        "conversations_24h": 0,
    },
    "personality": {
        "sir_frequency": 0.3,
        "avg_response_words": 40,
        "tone": "british_professional",
    },
    "capability_inventory": {},
    "recent_topics": [],
    "improvement_notes": [],
}

# ── Correction / positive signal patterns ────────────────────────────────

_CORRECTION_PATTERNS = re.compile(
    r"\b(no[,.]?\s|that'?s wrong|that is wrong|try again|incorrect|not right|"
    r"wrong answer|you'?re wrong|nope|stop)\b",
    re.IGNORECASE,
)

_POSITIVE_PATTERNS = re.compile(
    r"\b(thanks|thank you|perfect|great|excellent|awesome|good job|well done|"
    r"nice work|love it|exactly|correct)\b",
    re.IGNORECASE,
)


# ═════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════


async def run_awareness_cycle() -> dict[str, Any]:
    """Execute a full awareness cycle: evaluate, update model, calibrate.

    Returns a summary dict describing what changed.
    """
    try:
        logger.info("Awareness cycle starting")

        # Phase 1 — evaluate recent interactions
        evaluation = await _evaluate_recent_interactions(since_minutes=60)

        # Phase 2 — update the self-model
        updated_model = await _update_self_model(evaluation)

        # Phase 3 — calibrate personality from recent messages
        messages = evaluation.get("messages_raw", [])
        personality = await _calibrate_personality(messages)
        updated_model["personality"] = {
            **updated_model.get("personality", {}),
            **personality,
        }

        # Persist final model
        redis = await get_redis_client()
        updated_model["last_updated"] = datetime.now(timezone.utc).isoformat()
        await redis.cache_set(_SELF_MODEL_KEY, json.dumps(updated_model), ttl=_TTL_365_DAYS)

        # Store daily snapshot
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history_key = f"{_HISTORY_PREFIX}:{date_key}"
        await redis.cache_set(history_key, json.dumps(updated_model), ttl=_TTL_30_DAYS)

        result = {
            "status": "completed",
            "timestamp": updated_model["last_updated"],
            "messages_analyzed": evaluation.get("total_messages", 0),
            "corrections_found": evaluation.get("corrections", 0),
            "positive_signals": evaluation.get("positive_signals", 0),
            "personality": personality,
        }
        logger.info("Awareness cycle completed: %d messages analyzed", result["messages_analyzed"])
        return result

    except Exception:
        logger.exception("Awareness cycle failed")
        return {"status": "error", "timestamp": datetime.now(timezone.utc).isoformat()}


async def get_self_model() -> dict[str, Any]:
    """Return the current self-model from Redis, or the default if none exists."""
    try:
        redis = await get_redis_client()
        raw = await redis.cache_get(_SELF_MODEL_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        logger.warning("Failed to load self-model from Redis", exc_info=True)
    return {**_DEFAULT_SELF_MODEL, "last_updated": ""}


async def run_cross_ai_pollination(topic: str, context: str) -> dict[str, Any]:
    """Query Perplexity for an outside perspective and synthesize insights.

    Uses the perplexity_research tool from the agent registry to gather
    external information, then compares it with JARVIS's own understanding.
    """
    try:
        from app.agents.tools import get_tool_registry

        registry = get_tool_registry()
        perplexity = registry.get("perplexity_research")
        if perplexity is None:
            return {"error": "Perplexity research tool not available"}

        query = f"{topic}: {context}"
        external_result = await perplexity.execute({"query": query, "max_tokens": 1024})

        # Use Gemini to synthesise JARVIS's own perspective with external info
        llm = get_llm_client("gemini")
        synthesis_prompt = [
            {
                "role": "system",
                "content": (
                    "You are JARVIS's self-reflection module. Compare an external AI's "
                    "perspective with JARVIS's internal context and produce a brief synthesis "
                    "noting agreements, disagreements, and new insights."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Topic: {topic}\n\n"
                    f"JARVIS context:\n{context}\n\n"
                    f"External perspective:\n{external_result}"
                ),
            },
        ]
        response = await llm.chat_completion(synthesis_prompt, temperature=0.4, max_tokens=512)
        synthesis = response.get("content", "")

        return {
            "topic": topic,
            "external_summary": external_result[:500],
            "synthesis": synthesis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception:
        logger.exception("Cross-AI pollination failed for topic: %s", topic)
        return {"error": "Cross-AI pollination failed", "topic": topic}


# ═════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════


async def _evaluate_recent_interactions(since_minutes: int = 60) -> dict[str, Any]:
    """Query PostgreSQL for recent messages and evaluate quality signals."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

    messages_raw: list[dict[str, Any]] = []
    corrections = 0
    positive_signals = 0
    assistant_count = 0
    user_count = 0
    total_latency_ms = 0.0
    latency_count = 0
    conversation_ids: set[str] = set()

    try:
        async with async_session_factory() as session:
            stmt = (
                select(Message)
                .where(Message.created_at >= cutoff)
                .order_by(Message.created_at.asc())
            )
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

            for msg in db_messages:
                content = msg.content or ""
                role = msg.role or ""
                messages_raw.append({
                    "role": role,
                    "content": content,
                    "conversation_id": str(msg.conversation_id),
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                    "latency_ms": msg.latency_ms,
                })
                conversation_ids.add(str(msg.conversation_id))

                if role == "user":
                    user_count += 1
                    if _CORRECTION_PATTERNS.search(content):
                        corrections += 1
                    if _POSITIVE_PATTERNS.search(content):
                        positive_signals += 1
                elif role == "assistant":
                    assistant_count += 1
                    if msg.latency_ms and msg.latency_ms > 0:
                        total_latency_ms += msg.latency_ms
                        latency_count += 1

    except Exception:
        logger.exception("Failed to query recent messages")

    avg_latency = total_latency_ms / latency_count if latency_count > 0 else 0

    evaluation: dict[str, Any] = {
        "total_messages": len(messages_raw),
        "user_messages": user_count,
        "assistant_messages": assistant_count,
        "corrections": corrections,
        "positive_signals": positive_signals,
        "avg_latency_ms": round(avg_latency, 1),
        "conversations": len(conversation_ids),
        "messages_raw": messages_raw,
    }

    # Use Gemini for quality analysis if we have enough data
    if len(messages_raw) >= 4:
        evaluation["quality_analysis"] = await _llm_quality_analysis(messages_raw[:50])

    return evaluation


async def _llm_quality_analysis(messages: list[dict[str, Any]]) -> str:
    """Ask Gemini to briefly assess conversation quality."""
    try:
        llm = get_llm_client("gemini")
        conversation_text = "\n".join(
            f"[{m['role']}]: {m['content'][:200]}" for m in messages
        )
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a quality analyst for JARVIS, a personal AI assistant. "
                    "Review the following conversation excerpts and provide a 2-3 sentence "
                    "assessment of response quality, helpfulness, and tone. Note any issues."
                ),
            },
            {"role": "user", "content": conversation_text},
        ]
        response = await llm.chat_completion(prompt, temperature=0.3, max_tokens=256)
        return response.get("content", "")
    except Exception:
        logger.warning("LLM quality analysis failed", exc_info=True)
        return ""


async def _update_self_model(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Merge evaluation data into the persistent self-model."""
    model = await get_self_model()

    # Update performance metrics using exponential moving averages
    perf = model.get("performance", {})
    new_latency = evaluation.get("avg_latency_ms", 0)
    if new_latency > 0:
        old = perf.get("avg_response_time_ms", 0)
        perf["avg_response_time_ms"] = round(
            _ema(old, new_latency) if old > 0 else new_latency, 1
        )

    perf["user_corrections_24h"] = evaluation.get("corrections", 0)
    perf["conversations_24h"] = evaluation.get("conversations", 0)
    model["performance"] = perf

    # Track recent topics from conversation content
    topics = _extract_topics(evaluation.get("messages_raw", []))
    existing_topics = model.get("recent_topics", [])
    merged_topics = list(dict.fromkeys(topics + existing_topics))[:20]
    model["recent_topics"] = merged_topics

    # Update strengths/weaknesses based on accumulated signals
    # Require 3 consecutive positive/negative signals before modifying lists
    quality = evaluation.get("quality_analysis", "")
    if quality:
        notes = model.get("improvement_notes", [])
        notes.insert(0, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "analysis": quality[:500],
            "corrections": evaluation.get("corrections", 0),
            "positive": evaluation.get("positive_signals", 0),
        })
        model["improvement_notes"] = notes[:10]

        # Promote to strengths/weaknesses only with 3 consecutive signals
        _update_strengths_weaknesses(model)

    # Persist
    redis = await get_redis_client()
    model["last_updated"] = datetime.now(timezone.utc).isoformat()
    await redis.cache_set(_SELF_MODEL_KEY, json.dumps(model), ttl=_TTL_365_DAYS)

    return model


async def _calibrate_personality(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure sir frequency and verbosity from assistant responses."""
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_messages:
        return {"sir_frequency": 0.3, "avg_response_words": 40, "tone": "british_professional"}

    sir_count = 0
    total_words = 0

    for msg in assistant_messages:
        content = msg.get("content", "")
        words = content.split()
        total_words += len(words)
        sir_count += len(re.findall(r"\bsir\b", content, re.IGNORECASE))

    avg_words = total_words / len(assistant_messages) if assistant_messages else 40
    sir_freq = sir_count / len(assistant_messages) if assistant_messages else 0.3

    # Determine tone assessment
    if 0.25 <= sir_freq <= 0.35 and 30 <= avg_words <= 60:
        tone = "appropriately_british"
    elif sir_freq > 0.5:
        tone = "overly_formal"
    elif sir_freq < 0.1:
        tone = "insufficiently_british"
    elif avg_words > 80:
        tone = "verbose"
    elif avg_words < 20:
        tone = "terse"
    else:
        tone = "british_professional"

    return {
        "sir_frequency": round(sir_freq, 3),
        "avg_response_words": round(avg_words, 1),
        "tone": tone,
    }


# ── Pure helpers ─────────────────────────────────────────────────────────


def _ema(old: float, new: float, alpha: float = _EMA_ALPHA) -> float:
    """Exponential moving average: blend *old* with *new* using *alpha*."""
    return alpha * new + (1 - alpha) * old


def _extract_topics(messages: list[dict[str, Any]]) -> list[str]:
    """Pull rough topic keywords from user messages."""
    topics: list[str] = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        # Take the first few meaningful words as a topic tag
        words = content.split()[:6]
        if words:
            tag = " ".join(words).strip("?.!,")
            if len(tag) > 3:
                topics.append(tag[:60])
    return topics[:10]


def _update_strengths_weaknesses(model: dict[str, Any]) -> None:
    """Promote patterns to strengths/weaknesses after 3 consecutive signals."""
    notes = model.get("improvement_notes", [])
    if len(notes) < 3:
        return

    recent_3 = notes[:3]

    # Check for consistent corrections → weakness
    if all(n.get("corrections", 0) > 0 for n in recent_3):
        weakness = "frequent corrections detected"
        weaknesses = model.get("weaknesses", [])
        if weakness not in weaknesses:
            weaknesses.append(weakness)
            model["weaknesses"] = weaknesses[:10]

    # Check for consistent positives → strength
    if all(n.get("positive", 0) > 0 for n in recent_3):
        strength = "consistently positive user feedback"
        strengths = model.get("strengths", [])
        if strength not in strengths:
            strengths.append(strength)
            model["strengths"] = strengths[:10]

    # Remove contradictions: if both correction and positive patterns break, clear
    if all(n.get("corrections", 0) == 0 for n in recent_3):
        weaknesses = model.get("weaknesses", [])
        if "frequent corrections detected" in weaknesses:
            weaknesses.remove("frequent corrections detected")
            model["weaknesses"] = weaknesses
