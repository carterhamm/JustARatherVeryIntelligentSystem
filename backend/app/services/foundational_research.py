"""
Foundational research ingestion for JARVIS.

Ingests comprehensive knowledge about key figures and fields that inform
Mr. Stark's nanotechnology research:
  - Nikola Tesla: wireless energy, resonance, field theory, patents
  - John Pendry: metamaterials, superlens, near-field energy transfer
  - Feynman: handled separately in feynman_ingestion.py

Uses web search → scraping → knowledge base ingestion pipeline.
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("jarvis.foundational_research")

# ═══════════════════════════════════════════════════════════════════════════
# Research targets — topics to deeply research and ingest
# ═══════════════════════════════════════════════════════════════════════════

RESEARCH_TARGETS = [
    # ── Tesla ──────────────────────────────────────────────────────
    {
        "name": "tesla_wireless_energy",
        "label": "Tesla: Wireless Energy Transmission",
        "queries": [
            "Nikola Tesla wireless energy transmission theory experiments",
            "Tesla Wardenclyffe Tower wireless power technical details",
            "Tesla resonant inductive coupling original papers",
            "Tesla magnifying transmitter technical specifications",
        ],
    },
    {
        "name": "tesla_resonance",
        "label": "Tesla: Resonance & Oscillation Theory",
        "queries": [
            "Nikola Tesla mechanical electrical resonance experiments",
            "Tesla oscillator earthquake machine technical analysis",
            "Tesla resonance frequency energy amplification theory",
            "resonant energy transfer Tesla principles physics",
        ],
    },
    {
        "name": "tesla_electromagnetic",
        "label": "Tesla: Electromagnetic Field Manipulation",
        "queries": [
            "Tesla rotating magnetic field invention details",
            "Tesla coil electromagnetic principles physics derivation",
            "Tesla high frequency high voltage experiments technical",
            "Nikola Tesla electromagnetic field theory contributions",
        ],
    },
    {
        "name": "tesla_patents",
        "label": "Tesla: Key Patents & Inventions",
        "queries": [
            "Nikola Tesla most important patents list details",
            "Tesla alternating current motor patent technical",
            "Tesla radio patent technical specifications",
            "Tesla bladeless turbine patent analysis efficiency",
        ],
    },
    {
        "name": "tesla_energy_vision",
        "label": "Tesla: Vision for Free Energy & Field Theory",
        "queries": [
            "Tesla free energy concept scientific analysis",
            "Tesla scalar waves longitudinal waves theory",
            "Nikola Tesla ether theory electromagnetic medium",
            "Tesla radiant energy patent analysis physics",
        ],
    },
    # ── Pendry & Metamaterials ─────────────────────────────────────
    {
        "name": "pendry_negative_refraction",
        "label": "Pendry: Negative Refraction & Superlens",
        "queries": [
            "John Pendry negative refractive index metamaterial paper",
            "Pendry perfect lens superlens theory derivation",
            "negative refraction metamaterial experimental verification",
            "Pendry transformation optics principles",
        ],
    },
    {
        "name": "pendry_cloaking",
        "label": "Pendry: Electromagnetic Cloaking",
        "queries": [
            "Pendry electromagnetic cloaking metamaterial theory",
            "transformation optics invisibility cloak physics",
            "metamaterial cloaking experimental progress 2026",
            "Pendry Smith metamaterial design principles",
        ],
    },
    {
        "name": "metamaterials_energy",
        "label": "Metamaterials: Near-Field Energy Transfer",
        "queries": [
            "metamaterials near-field energy transfer concentration",
            "metamaterial wireless power transfer efficiency",
            "negative index material energy focusing nanoscale",
            "metamaterial enhanced Forster resonance energy transfer",
        ],
    },
    {
        "name": "metamaterials_acoustic",
        "label": "Metamaterials: Acoustic & Mechanical",
        "queries": [
            "acoustic metamaterials sound manipulation nanoscale",
            "phononic crystal bandgap engineering applications",
            "mechanical metamaterials programmable properties",
            "auxetic metamaterial negative Poisson ratio applications",
        ],
    },
    # ── Quantum Biology Foundations ─────────────────────────────────
    {
        "name": "quantum_biology_foundations",
        "label": "Quantum Biology: Comprehensive Foundation",
        "queries": [
            "quantum biology comprehensive review 2026",
            "quantum effects biological systems evidence",
            "quantum coherence warm wet biological systems",
            "Jim Al-Khalili quantum biology book summary key findings",
        ],
    },
    # ── DNA Nanotechnology ────────────────────────────────────────
    {
        "name": "dna_nanotech_foundation",
        "label": "DNA Nanotechnology: Rothemund & Beyond",
        "queries": [
            "Paul Rothemund DNA origami foundational paper",
            "DNA nanotechnology programmable matter review 2026",
            "DNA nanorobot drug delivery cancer treatment progress",
            "DNA brick self-assembly 3D nanostructures",
        ],
    },
]


async def ingest_foundational_research(
    targets: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Research and ingest foundational knowledge into the JARVIS knowledge base.

    Parameters
    ----------
    targets : list[str], optional
        Filter to specific target names (e.g. ["tesla_wireless_energy"]).
        If None, ingests all targets.

    Returns summary dict.
    """
    from app.agents.tools import get_tool_registry
    from app.db.redis import get_redis_client
    from app.integrations.llm.factory import get_llm_client
    from app.services.continuous_learning import ingest_research_finding
    from app.services.web_scraper import deep_research_topic

    redis = await get_redis_client()
    registry = get_tool_registry()
    search_tool = registry.get("web_search")
    llm = get_llm_client("gemini")

    start = _time.perf_counter()

    # Filter targets if specified
    research_list = RESEARCH_TARGETS
    if targets:
        research_list = [t for t in RESEARCH_TARGETS if t["name"] in targets]

    results = {
        "status": "ok",
        "targets_processed": 0,
        "documents_ingested": 0,
        "entities_found": 0,
        "errors": [],
    }

    for target in research_list:
        logger.info("Researching: %s", target["label"])

        # Check if already ingested
        done_key = f"jarvis:foundational:ingested:{target['name']}"
        if await redis.cache_get(done_key):
            logger.info("Already ingested: %s — skipping", target["name"])
            continue

        # Run web searches
        raw_parts: list[str] = []
        for query in target["queries"]:
            try:
                if search_tool:
                    result = await search_tool.run({"query": query, "max_results": 5})
                    if result and len(result) > 50:
                        raw_parts.append(f"### {query}\n{result}")
            except Exception as exc:
                logger.debug("Search failed for '%s': %s", query, exc)

        if not raw_parts:
            results["errors"].append(f"{target['name']}: no search results")
            continue

        combined = "\n\n".join(raw_parts)

        # Deep scrape for richer content
        scraped_articles = await deep_research_topic(
            topic_label=target["label"],
            search_results=combined,
            max_urls=3,
        )

        # Summarise with Gemini
        try:
            response = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": (
                        "You are compiling comprehensive technical knowledge. "
                        "Be thorough, specific, and include equations/formulas where relevant. "
                        "Preserve technical detail — this will be used as reference material."
                    )},
                    {"role": "user", "content": (
                        f"Topic: {target['label']}\n\n"
                        f"Compile a comprehensive, detailed technical summary (600-1000 words) "
                        f"from this research. Include specific technical details, equations, "
                        f"dates, names, and experimental results.\n\n"
                        f"{combined[:10000]}"
                    )},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            summary = response["content"].strip()
        except Exception as exc:
            logger.warning("Summarization failed for %s: %s", target["name"], exc)
            summary = combined[:3000]

        # Ingest summary
        ingested = await ingest_research_finding({
            "topic": target["name"],
            "label": target["label"],
            "summary": summary,
            "source": "foundational_research",
            "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
        })

        if ingested:
            results["documents_ingested"] += 1
            results["entities_found"] += ingested.get("entity_count", 0)

        # Ingest scraped articles
        for article in scraped_articles:
            if article.get("success") and article.get("content"):
                art_ingested = await ingest_research_finding({
                    "topic": f"{target['name']}_article",
                    "label": article.get("title", target["label"]),
                    "summary": article["content"],
                    "source": f"foundational_scrape:{article.get('url', '')}",
                    "date": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
                })
                if art_ingested:
                    results["documents_ingested"] += 1
                    results["entities_found"] += art_ingested.get("entity_count", 0)

        # Mark as done
        await redis.cache_set(done_key, "1", ttl=86400 * 365)
        results["targets_processed"] += 1

        logger.info("Completed: %s", target["label"])

    elapsed_ms = int((_time.perf_counter() - start) * 1000)
    results["total_time_ms"] = elapsed_ms

    logger.info(
        "Foundational research complete: %d targets, %d docs, %d entities, %.1fs",
        results["targets_processed"], results["documents_ingested"],
        results["entities_found"], elapsed_ms / 1000,
    )

    return results


async def get_foundational_status() -> dict[str, Any]:
    """Check which foundational research targets have been ingested."""
    from app.db.redis import get_redis_client
    redis = await get_redis_client()

    status: list[dict[str, Any]] = []
    for target in RESEARCH_TARGETS:
        done_key = f"jarvis:foundational:ingested:{target['name']}"
        done = await redis.cache_get(done_key)
        status.append({
            "name": target["name"],
            "label": target["label"],
            "ingested": done is not None,
        })

    return {
        "total": len(RESEARCH_TARGETS),
        "ingested": sum(1 for s in status if s["ingested"]),
        "pending": sum(1 for s in status if not s["ingested"]),
        "targets": status,
    }
