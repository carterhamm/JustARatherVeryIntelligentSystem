"""
Continuous learning orchestrator for JARVIS.

Coordinates all Phase 2 learning subsystems:
  1. Enhanced research (fixed + trending topics)
  2. Deep web scraping (full article content)
  3. Knowledge ingestion (research → Qdrant/Neo4j)
  4. Internal dialogue (dual-LLM debate)
  5. Learning metrics tracking

The main entry point is `run_learning_cycle()`, called by the
`/cron/learning-cycle` endpoint.

Part of Phase 2: Continuous Learning (Days 3-5).
"""

from __future__ import annotations

import json
import logging
import time as _time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.continuous_learning")

# Redis keys for learning metrics
_KEY_METRICS = "jarvis:learning:metrics"
_KEY_CYCLE_LOG = "jarvis:learning:cycle_log"
_KEY_TOTAL_INGESTED = "jarvis:learning:total_ingested"
_KEY_TOTAL_ENTITIES = "jarvis:learning:total_entities"
_KEY_TOTAL_DIALOGUES = "jarvis:learning:total_dialogues"
_KEY_LAST_CYCLE = "jarvis:learning:last_cycle"
_METRICS_TTL = 86400 * 365  # 1 year


async def run_learning_cycle(
    include_trending: bool = True,
    include_deep_scrape: bool = True,
    include_dialogue: bool = True,
) -> dict[str, Any]:
    """Execute a full continuous learning cycle.

    Steps:
    1. Run standard research daemon (one fixed topic)
    2. Detect trending topics and research them
    3. Deep-scrape article URLs from search results
    4. Auto-ingest all findings into Qdrant/Neo4j
    5. Run internal dialogue on the most interesting finding
    6. Update learning metrics

    Returns cycle metadata dict.
    """
    from app.services.research_daemon import run_research_cycle, RESEARCH_TOPICS
    from app.db.redis import get_redis_client

    cycle_start = _time.perf_counter()
    redis = await get_redis_client()
    now = datetime.now(tz=timezone.utc)

    logger.info("═══════════════════════════════════════════════════════")
    logger.info("CONTINUOUS LEARNING: cycle starting")
    logger.info("═══════════════════════════════════════════════════════")

    results: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "phases": {},
        "total_ingested": 0,
        "total_entities": 0,
        "errors": [],
    }

    # ── Phase 1: Standard research (fixed topic rotation) ──────────
    logger.info("Phase 1: Standard research cycle")
    try:
        research_result = await run_research_cycle()
        results["phases"]["research"] = {
            "status": research_result.get("status", "unknown"),
            "topic": research_result.get("label", ""),
            "summary_length": research_result.get("summary_length", 0),
        }

        # Auto-ingest the research finding into knowledge base
        if research_result.get("status") == "ok":
            summary = research_result.get("summary_preview", "")
            if len(summary) < 200:
                # Fetch full summary from Redis
                from app.services.research_daemon import get_research_summary
                full = await get_research_summary(
                    topic=research_result.get("topic", ""), days=1,
                )
                if full and len(full) > len(summary):
                    summary = full

            ingested = await ingest_research_finding({
                "topic": research_result.get("topic", ""),
                "label": research_result.get("label", "Research Finding"),
                "summary": summary,
                "source": "research_daemon",
                "date": research_result.get("date", now.strftime("%Y-%m-%d")),
            })
            if ingested:
                results["total_ingested"] += 1
                results["total_entities"] += ingested.get("entity_count", 0)

    except Exception as exc:
        logger.exception("Phase 1 (research) failed: %s", exc)
        results["phases"]["research"] = {"status": "error", "error": str(exc)}
        results["errors"].append(f"research: {exc}")

    # ── Phase 2: Trending topics ───────────────────────────────────
    if include_trending:
        logger.info("Phase 2: Trending topic detection + research")
        try:
            from app.services.trend_detector import get_personalized_topics
            trending = await get_personalized_topics(count=2)

            trend_results = []
            for topic in trending:
                trend_finding = await _research_trending_topic(topic)
                if trend_finding:
                    ingested = await ingest_research_finding(trend_finding)
                    if ingested:
                        results["total_ingested"] += 1
                        results["total_entities"] += ingested.get("entity_count", 0)
                    trend_results.append({
                        "topic": topic["name"],
                        "label": topic["label"],
                        "relevance": topic.get("relevance_score", 0),
                        "ingested": ingested is not None,
                    })

            results["phases"]["trending"] = {
                "status": "ok",
                "topics_found": len(trending),
                "topics_researched": len(trend_results),
                "details": trend_results,
            }
        except Exception as exc:
            logger.exception("Phase 2 (trending) failed: %s", exc)
            results["phases"]["trending"] = {"status": "error", "error": str(exc)}
            results["errors"].append(f"trending: {exc}")
    else:
        results["phases"]["trending"] = {"status": "skipped"}

    # ── Phase 3: Deep scraping ─────────────────────────────────────
    if include_deep_scrape:
        logger.info("Phase 3: Deep web scraping")
        try:
            scrape_results = await _deep_scrape_latest_research()
            results["phases"]["deep_scrape"] = scrape_results
            results["total_ingested"] += scrape_results.get("ingested_count", 0)
            results["total_entities"] += scrape_results.get("entity_count", 0)
        except Exception as exc:
            logger.exception("Phase 3 (deep scrape) failed: %s", exc)
            results["phases"]["deep_scrape"] = {"status": "error", "error": str(exc)}
            results["errors"].append(f"deep_scrape: {exc}")
    else:
        results["phases"]["deep_scrape"] = {"status": "skipped"}

    # ── Phase 4: Internal dialogue ─────────────────────────────────
    if include_dialogue:
        logger.info("Phase 4: Internal dialogue")
        try:
            dialogue_result = await _run_dialogue_on_latest()
            results["phases"]["dialogue"] = {
                "status": "ok",
                "topic": dialogue_result.get("topic", ""),
                "rounds": dialogue_result.get("rounds", 0),
                "insights_found": len(dialogue_result.get("insights", [])),
            }

            # Ingest dialogue insights as knowledge
            insights = dialogue_result.get("insights", [])
            if insights:
                insight_text = _format_insights_for_ingestion(
                    dialogue_result["topic"], insights,
                )
                ingested = await ingest_research_finding({
                    "topic": f"dialogue_{dialogue_result['topic']}",
                    "label": f"Dialogue Insights: {dialogue_result['topic']}",
                    "summary": insight_text,
                    "source": "internal_dialogue",
                    "date": now.strftime("%Y-%m-%d"),
                })
                if ingested:
                    results["total_ingested"] += 1
                    results["total_entities"] += ingested.get("entity_count", 0)

        except Exception as exc:
            logger.exception("Phase 4 (dialogue) failed: %s", exc)
            results["phases"]["dialogue"] = {"status": "error", "error": str(exc)}
            results["errors"].append(f"dialogue: {exc}")
    else:
        results["phases"]["dialogue"] = {"status": "skipped"}

    # ── Update metrics ─────────────────────────────────────────────
    elapsed_ms = int((_time.perf_counter() - cycle_start) * 1000)
    results["total_time_ms"] = elapsed_ms
    results["status"] = "ok" if not results["errors"] else "partial"

    await _update_metrics(results, redis)

    # ── Phase 5: Notify Mr. Stark via iMessage ─────────────────────
    await _notify_learning_results(results)

    logger.info("═══════════════════════════════════════════════════════")
    logger.info(
        "CONTINUOUS LEARNING: cycle complete — "
        "ingested=%d, entities=%d, errors=%d, total=%.1fs",
        results["total_ingested"],
        results["total_entities"],
        len(results["errors"]),
        elapsed_ms / 1000,
    )
    logger.info("═══════════════════════════════════════════════════════")

    return results


async def ingest_research_finding(finding: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Ingest a research finding into Qdrant and Neo4j.

    Takes a dict with:
        - topic: str (topic name)
        - label: str (human-readable label)
        - summary: str (the content to ingest)
        - source: str (where it came from)
        - date: str (date string)

    Returns ingestion metadata or None on failure.
    """
    summary = finding.get("summary", "")
    if not summary or len(summary) < 50:
        logger.debug("Skipping ingestion — summary too short (%d chars)", len(summary))
        return None

    try:
        from app.db.neo4j import get_neo4j_client
        from app.db.qdrant import get_qdrant_store
        from app.db.session import async_session_factory
        from app.graphrag.entity_extractor import EntityExtractor
        from app.graphrag.graph_store import GraphStore
        from app.graphrag.hybrid_retriever import HybridRetriever
        from app.graphrag.vector_store import VectorStore
        from app.schemas.knowledge import KnowledgeIngest
        from app.services.knowledge_service import KnowledgeService

        neo4j_client = get_neo4j_client()
        qdrant_store = get_qdrant_store()

        entity_extractor = EntityExtractor()
        graph_store = GraphStore(neo4j_client=neo4j_client)
        vector_store = VectorStore(qdrant_store=qdrant_store)
        hybrid_retriever = HybridRetriever(
            graph_store=graph_store,
            vector_store=vector_store,
            entity_extractor=entity_extractor,
        )

        async with async_session_factory() as db:
            service = KnowledgeService(
                db=db,
                hybrid_retriever=hybrid_retriever,
                entity_extractor=entity_extractor,
                graph_store=graph_store,
                vector_store=vector_store,
            )

            # Find the owner user ID
            from sqlalchemy import select
            from app.models.user import User
            result = await db.execute(
                select(User).where(User.is_active.is_(True)).limit(1)
            )
            owner = result.scalar_one_or_none()
            if not owner:
                logger.error("No active owner found for knowledge ingestion")
                return None

            # Build ingestion request
            title = f"{finding.get('label', 'Research')} ({finding.get('date', 'unknown')})"
            data = KnowledgeIngest(
                content=summary,
                source_type="research",
                title=title,
                metadata={
                    "topic": finding.get("topic", ""),
                    "source": finding.get("source", "learning"),
                    "date": finding.get("date", ""),
                    "auto_ingested": True,
                },
            )

            response = await service.ingest(user_id=owner.id, data=data)

            logger.info(
                "Ingested research finding: topic=%s, chunks=%d, entities=%d",
                finding.get("topic", ""),
                response.chunk_count or 0,
                response.entity_count or 0,
            )

            return {
                "source_id": str(response.id),
                "chunk_count": response.chunk_count or 0,
                "entity_count": response.entity_count or 0,
                "status": response.status,
            }

    except Exception as exc:
        logger.exception("Knowledge ingestion failed: %s", exc)
        return None


async def _research_trending_topic(topic: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Research a single trending topic and return a finding dict."""
    from app.agents.tools import get_tool_registry
    from app.integrations.llm.factory import get_llm_client

    registry = get_tool_registry()
    search_tool = registry.get("web_search")
    if not search_tool:
        return None

    queries = topic.get("queries", [f"{topic['label']} latest"])

    raw_parts: list[str] = []
    for query in queries[:3]:
        try:
            result = await search_tool.run({"query": query, "max_results": 4})
            if result and len(result) > 50:
                raw_parts.append(f"### {query}\n{result}")
        except Exception as exc:
            logger.debug("Trending search failed for '%s': %s", query, exc)

    if not raw_parts:
        return None

    # Summarise
    llm = get_llm_client("gemini")
    combined = "\n\n".join(raw_parts)[:8000]

    try:
        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": "You are JARVIS, compiling a concise research note."},
                {"role": "user", "content": (
                    f"Topic: {topic['label']}\n"
                    f"Context: {topic.get('description', '')}\n\n"
                    f"Search results:\n{combined}\n\n"
                    "Write a concise research brief (200-400 words) highlighting "
                    "the most important findings. Be factual, specific, and informative."
                )},
            ],
            temperature=0.4,
            max_tokens=600,
        )
        summary = response["content"].strip()
    except Exception as exc:
        logger.warning("Trending topic summarization failed: %s", exc)
        return None

    return {
        "topic": topic["name"],
        "label": topic["label"],
        "summary": summary,
        "source": "trending",
        "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
    }


async def _deep_scrape_latest_research() -> dict[str, Any]:
    """Deep-scrape the most recent research finding for richer content."""
    from app.db.redis import get_redis_client
    from app.services.web_scraper import deep_research_topic

    redis = await get_redis_client()
    result = {
        "status": "ok",
        "articles_scraped": 0,
        "ingested_count": 0,
        "entity_count": 0,
    }

    # Get latest research finding from Redis
    from app.services.research_daemon import RESEARCH_TOPICS, _KEY_LATEST_PREFIX
    best_finding = None
    best_summary = ""

    for topic in RESEARCH_TOPICS:
        raw = await redis.cache_get(f"{_KEY_LATEST_PREFIX}:{topic['name']}")
        if raw:
            try:
                finding = json.loads(raw)
                summary = finding.get("summary", "")
                if len(summary) > len(best_summary):
                    best_summary = summary
                    best_finding = finding
            except (json.JSONDecodeError, TypeError):
                pass

    if not best_finding:
        result["status"] = "no_findings"
        return result

    # Deep-scrape URLs from the summary
    articles = await deep_research_topic(
        topic_label=best_finding.get("label", ""),
        search_results=best_summary,
        max_urls=3,
    )

    result["articles_scraped"] = len(articles)

    # Ingest each scraped article
    for article in articles:
        if not article.get("success") or not article.get("content"):
            continue

        ingested = await ingest_research_finding({
            "topic": f"deep_{best_finding.get('topic', 'unknown')}",
            "label": article.get("title", "Scraped Article"),
            "summary": article["content"],
            "source": f"web_scrape:{article.get('url', '')}",
            "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        })

        if ingested:
            result["ingested_count"] += 1
            result["entity_count"] += ingested.get("entity_count", 0)

    return result


async def _run_dialogue_on_latest() -> dict[str, Any]:
    """Run an internal dialogue session on the most recent research finding."""
    from app.db.redis import get_redis_client
    from app.services.internal_dialogue import run_dialogue_session
    from app.services.research_daemon import RESEARCH_TOPICS, _KEY_LATEST_PREFIX

    redis = await get_redis_client()

    # Find the most recent finding
    best_finding = None
    best_ts = ""

    for topic in RESEARCH_TOPICS:
        raw = await redis.cache_get(f"{_KEY_LATEST_PREFIX}:{topic['name']}")
        if raw:
            try:
                finding = json.loads(raw)
                ts = finding.get("timestamp", "")
                if ts > best_ts:
                    best_ts = ts
                    best_finding = finding
            except (json.JSONDecodeError, TypeError):
                pass

    if not best_finding:
        return {"topic": "none", "rounds": 0, "insights": []}

    return await run_dialogue_session(
        topic=best_finding.get("label", "Unknown"),
        summary=best_finding.get("summary", ""),
        rounds=3,
        use_local_llm=True,
    )


def _format_insights_for_ingestion(
    topic: str,
    insights: list[dict[str, Any]],
) -> str:
    """Format extracted insights into a text document for knowledge ingestion."""
    lines = [
        f"# Dialogue Insights: {topic}",
        f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Key Insights",
        "",
    ]
    for i, ins in enumerate(insights, 1):
        category = ins.get("category", "general").upper()
        confidence = ins.get("confidence", 0.5)
        lines.append(
            f"{i}. [{category}] (confidence: {confidence:.1f}) {ins['insight']}"
        )

    return "\n".join(lines)


async def _update_metrics(
    cycle_result: dict[str, Any],
    redis: Any,
) -> None:
    """Update cumulative learning metrics in Redis."""
    try:
        # Update totals
        raw_ingested = await redis.cache_get(_KEY_TOTAL_INGESTED)
        total_ingested = int(raw_ingested) if raw_ingested else 0
        total_ingested += cycle_result.get("total_ingested", 0)
        await redis.cache_set(_KEY_TOTAL_INGESTED, str(total_ingested), ttl=_METRICS_TTL)

        raw_entities = await redis.cache_get(_KEY_TOTAL_ENTITIES)
        total_entities = int(raw_entities) if raw_entities else 0
        total_entities += cycle_result.get("total_entities", 0)
        await redis.cache_set(_KEY_TOTAL_ENTITIES, str(total_entities), ttl=_METRICS_TTL)

        # Store last cycle result
        await redis.cache_set(
            _KEY_LAST_CYCLE,
            json.dumps(cycle_result),
            ttl=86400 * 7,
        )

        # Append to today's log
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        log_key = f"{_KEY_CYCLE_LOG}:{today}"
        raw_log = await redis.cache_get(log_key)
        log_entries = json.loads(raw_log) if raw_log else []
        log_entries.append({
            "timestamp": cycle_result.get("timestamp", ""),
            "ingested": cycle_result.get("total_ingested", 0),
            "entities": cycle_result.get("total_entities", 0),
            "errors": len(cycle_result.get("errors", [])),
            "time_ms": cycle_result.get("total_time_ms", 0),
        })
        await redis.cache_set(log_key, json.dumps(log_entries), ttl=86400 * 7)

    except Exception:
        logger.debug("Failed to update learning metrics", exc_info=True)


async def _notify_learning_results(results: dict[str, Any]) -> None:
    """Send an iMessage to Mr. Stark with a summary of the learning cycle.

    Only sends if there's something interesting to report (insights,
    new trending topics, or notable findings). Skips boring cycles.
    """
    try:
        from app.config import settings
        from app.integrations.mac_mini import send_imessage, is_configured

        if not is_configured() or not settings.OWNER_PHONE:
            return

        # Only notify if something interesting happened
        total_ingested = results.get("total_ingested", 0)
        dialogue = results.get("phases", {}).get("dialogue", {})
        insights_count = dialogue.get("insights_found", 0)
        trending = results.get("phases", {}).get("trending", {})
        trending_count = trending.get("topics_found", 0)

        # Skip notification if nothing notable
        if total_ingested == 0 and insights_count == 0 and trending_count == 0:
            return

        from zoneinfo import ZoneInfo
        now = datetime.now(tz=ZoneInfo("America/Denver")).strftime("%I:%M %p")

        lines = [f"Learning Cycle Complete ({now})"]
        lines.append(f"Ingested {total_ingested} documents, discovered {results.get('total_entities', 0)} entities")

        # Research topic
        research = results.get("phases", {}).get("research", {})
        if research.get("status") == "ok" and research.get("topic"):
            lines.append(f"\nResearched: {research['topic']}")

        # Trending topics
        if trending_count > 0:
            trend_details = trending.get("details", [])
            trend_names = [t.get("label", t.get("topic", "")) for t in trend_details[:3]]
            if trend_names:
                lines.append(f"Trending: {', '.join(trend_names)}")

        # Dialogue insights (the most interesting part)
        if insights_count > 0:
            lines.append(f"\n{insights_count} insight(s) from internal debate on '{dialogue.get('topic', '')}'")

        # Errors
        errors = results.get("errors", [])
        if errors:
            lines.append(f"\n({len(errors)} phase(s) had errors)")

        message = "\n".join(lines)

        await send_imessage(to=settings.OWNER_PHONE, text=message)
        logger.info("Learning notification sent to owner")

    except Exception as exc:
        logger.debug("Learning notification failed (non-critical): %s", exc)


async def get_learning_metrics() -> dict[str, Any]:
    """Return current learning metrics for JARVIS.

    Used by the learning_status tool so JARVIS can report
    on its own knowledge growth.
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()

    total_ingested = await redis.cache_get(_KEY_TOTAL_INGESTED) or "0"
    total_entities = await redis.cache_get(_KEY_TOTAL_ENTITIES) or "0"
    total_dialogues = await redis.cache_get(_KEY_TOTAL_DIALOGUES) or "0"
    last_cycle_raw = await redis.cache_get(_KEY_LAST_CYCLE)

    last_cycle = None
    if last_cycle_raw:
        try:
            last_cycle = json.loads(last_cycle_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # Today's cycle log
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    log_raw = await redis.cache_get(f"{_KEY_CYCLE_LOG}:{today}")
    today_cycles = json.loads(log_raw) if log_raw else []

    # Get Qdrant point count (approximate knowledge size)
    knowledge_size = 0
    try:
        from app.db.qdrant import get_qdrant_store
        qdrant = get_qdrant_store()
        count = await qdrant.count()
        knowledge_size = count
    except Exception:
        pass

    return {
        "total_documents_ingested": int(total_ingested),
        "total_entities_discovered": int(total_entities),
        "total_dialogue_sessions": int(total_dialogues),
        "knowledge_base_size": knowledge_size,
        "today_cycles": len(today_cycles),
        "today_ingested": sum(c.get("ingested", 0) for c in today_cycles),
        "today_entities": sum(c.get("entities", 0) for c in today_cycles),
        "last_cycle": {
            "timestamp": last_cycle.get("timestamp", "") if last_cycle else "",
            "status": last_cycle.get("status", "") if last_cycle else "never_run",
            "ingested": last_cycle.get("total_ingested", 0) if last_cycle else 0,
            "phases": list(last_cycle.get("phases", {}).keys()) if last_cycle else [],
        },
    }
