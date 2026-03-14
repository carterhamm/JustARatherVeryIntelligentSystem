"""
Ingest The Feynman Lectures on Physics into the JARVIS knowledge base.

Fetches all 115 chapters (3 volumes) from feynmanlectures.caltech.edu,
extracts text content preserving LaTeX math notation, and ingests each
chapter into Qdrant (vector store) and Neo4j (graph store) via the
existing KnowledgeService pipeline.

Progress is tracked in Redis so ingestion can be resumed if interrupted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("jarvis.feynman_ingestion")

# ═══════════════════════════════════════════════════════════════════════════
# Chapter definitions — 115 chapters across 3 volumes
# ═══════════════════════════════════════════════════════════════════════════

FEYNMAN_VOLUMES: dict[int, dict[str, Any]] = {
    1: {
        "title": "The Feynman Lectures on Physics, Volume I: Mainly Mechanics, Radiation, and Heat",
        "url_prefix": "I",
        "chapters": {
            1: "Atoms in Motion",
            2: "Basic Physics",
            3: "The Relation of Physics to Other Sciences",
            4: "Conservation of Energy",
            5: "Time and Distance",
            6: "Probability",
            7: "The Theory of Gravitation",
            8: "Motion",
            9: "Newton's Laws of Dynamics",
            10: "Conservation of Momentum",
            11: "Vectors",
            12: "Characteristics of Force",
            13: "Work and Potential Energy (A)",
            14: "Work and Potential Energy (conclusion)",
            15: "The Special Theory of Relativity",
            16: "Relativistic Energy and Momentum",
            17: "Space-Time",
            18: "Rotation in Two Dimensions",
            19: "Center of Mass; Moment of Inertia",
            20: "Rotation in Space",
            21: "The Harmonic Oscillator",
            22: "Algebra",
            23: "Resonance",
            24: "Transients",
            25: "Linear Systems and Review",
            26: "Optics: The Principle of Least Time",
            27: "Geometrical Optics",
            28: "Electromagnetic Radiation",
            29: "Interference",
            30: "Diffraction",
            31: "The Origin of the Refractive Index",
            32: "Radiation Damping. Light Scattering",
            33: "Polarization",
            34: "Relativistic Effects in Radiation",
            35: "Color Vision",
            36: "Mechanisms of Seeing",
            37: "Quantum Behavior",
            38: "The Relation of Wave and Particle Viewpoints",
            39: "The Kinetic Theory of Gases",
            40: "The Principles of Statistical Mechanics",
            41: "The Brownian Movement",
            42: "Applications of Kinetic Theory",
            43: "Diffusion",
            44: "The Laws of Thermodynamics",
            45: "Illustrations of Thermodynamics",
            46: "Ratchet and Pawl",
            47: "Sound. The Wave Equation",
            48: "Beats",
            49: "Modes",
            50: "Harmonics",
            51: "Waves",
            52: "Symmetry in Physical Laws",
        },
    },
    2: {
        "title": "The Feynman Lectures on Physics, Volume II: Mainly Electromagnetism and Matter",
        "url_prefix": "II",
        "chapters": {
            1: "Electromagnetism",
            2: "Differential Calculus of Vector Fields",
            3: "Vector Integral Calculus",
            4: "Electrostatics",
            5: "Application of Gauss' Law",
            6: "The Electric Field in Various Circumstances",
            7: "The Electric Field in Various Circumstances (continued)",
            8: "Electrostatic Energy",
            9: "Electricity in the Atmosphere",
            10: "Dielectrics",
            11: "Inside Dielectrics",
            12: "Electrostatic Analogs",
            13: "Magnetostatics",
            14: "The Magnetic Field in Various Situations",
            15: "The Vector Potential",
            16: "Induced Currents",
            17: "The Laws of Induction",
            18: "The Maxwell Equations",
            19: "The Principle of Least Action",
            20: "Solutions of Maxwell's Equations in Free Space",
            21: "Solutions of Maxwell's Equations with Currents and Charges",
            22: "AC Circuits",
            23: "Cavity Resonators",
            24: "Waveguides",
            25: "Electrodynamics in Relativistic Notation",
            26: "Lorentz Transformations of the Fields",
            27: "Field Energy and Field Momentum",
            28: "Electromagnetic Mass",
            29: "The Motion of Charges in Electric and Magnetic Fields",
            30: "The Internal Geometry of Crystals",
            31: "Tensors",
            32: "Refractive Index of Dense Materials",
            33: "Surface Reflection",
            34: "The Magnetism of Matter",
            35: "Paramagnetism and Magnetic Resonance",
            36: "Ferromagnetism",
            37: "Magnetic Materials",
            38: "Elasticity",
            39: "Elastic Materials",
            40: "The Flow of Dry Water",
            41: "The Flow of Wet Water",
            42: "Curved Space",
        },
    },
    3: {
        "title": "The Feynman Lectures on Physics, Volume III: Quantum Mechanics",
        "url_prefix": "III",
        "chapters": {
            1: "Quantum Behavior",
            2: "The Relation of Wave and Particle Viewpoints",
            3: "Probability Amplitudes",
            4: "Identical Particles",
            5: "Spin One",
            6: "Spin One-Half",
            7: "The Dependence of Amplitudes on Time",
            8: "The Hamiltonian Matrix",
            9: "The Ammonia Maser",
            10: "Other Two-State Systems",
            11: "More Two-State Systems",
            12: "The Hyperfine Splitting in Hydrogen",
            13: "Propagation in a Crystal Lattice",
            14: "Semiconductors",
            15: "The Independent Particle Approximation",
            16: "The Dependence of Amplitudes on Position",
            17: "Symmetry and Conservation Laws",
            18: "Angular Momentum",
            19: "The Hydrogen Atom and the Periodic Table",
            20: "Operators",
            21: "The Schrodinger Equation in a Classical Context: A Seminar on Superconductivity",
        },
    },
}

_BASE_URL = "https://www.feynmanlectures.caltech.edu"

# Redis keys
_PROGRESS_KEY = "jarvis:feynman:progress"
_INGESTED_PREFIX = "jarvis:feynman:ingested"
_LOCK_KEY = "jarvis:feynman:lock"
_METRICS_TTL = 86400 * 365  # 1 year


def _build_chapter_url(vol_prefix: str, chapter_num: int) -> str:
    """Build the URL for a specific Feynman Lectures chapter."""
    return f"{_BASE_URL}/{vol_prefix}_{chapter_num:02d}.html"


def _get_total_chapters(volumes: Optional[list[int]] = None) -> int:
    """Count total chapters across requested volumes."""
    total = 0
    for vol_num, vol_data in FEYNMAN_VOLUMES.items():
        if volumes and vol_num not in volumes:
            continue
        total += len(vol_data["chapters"])
    return total


def _extract_text(html: str, preserve_latex: bool = True) -> str:
    """Extract lecture text from Feynman Lectures HTML.

    Preserves LaTeX math notation (\\(...\\) and \\[...\\]) since LLMs
    can understand it.  Strips navigation, headers, footers, and scripts.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove nav, footer, scripts, styles
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # The main lecture content is typically in a div with class "chapter"
    # or the main body content area
    content_div = (
        soup.find("div", class_="chapter")
        or soup.find("div", id="chapter")
        or soup.find("div", class_="content")
        or soup.find("div", id="content")
        or soup.find("body")
    )

    if not content_div:
        content_div = soup

    if preserve_latex:
        # Replace MathJax script delimiters that may be in the page
        # The Feynman site uses \( ... \) for inline and \[ ... \] for display
        text = content_div.get_text(separator="\n", strip=False)
    else:
        text = content_div.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace while preserving paragraph breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    return text


async def _build_knowledge_service():
    """Build a KnowledgeService instance with all required dependencies."""
    from app.db.neo4j import get_neo4j_client
    from app.db.qdrant import get_qdrant_store
    from app.db.session import async_session_factory
    from app.graphrag.entity_extractor import EntityExtractor
    from app.graphrag.graph_store import GraphStore
    from app.graphrag.hybrid_retriever import HybridRetriever
    from app.graphrag.vector_store import VectorStore
    from app.services.knowledge_service import KnowledgeService
    from sqlalchemy import select
    from app.models.user import User

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

    db = async_session_factory()
    session = await db.__aenter__()

    # Find the owner user
    result = await session.execute(
        select(User).where(User.is_active.is_(True)).limit(1)
    )
    owner = result.scalar_one_or_none()
    if not owner:
        await db.__aexit__(None, None, None)
        raise RuntimeError("No active owner found for knowledge ingestion")

    service = KnowledgeService(
        db=session,
        hybrid_retriever=hybrid_retriever,
        entity_extractor=entity_extractor,
        graph_store=graph_store,
        vector_store=vector_store,
    )

    return service, owner, db


async def ingest_feynman_lectures(
    volumes: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Ingest The Feynman Lectures on Physics into the JARVIS knowledge base.

    Args:
        volumes: Optional list of volume numbers (1, 2, 3) to ingest.
                 None or empty means ingest all three volumes.

    Returns:
        Summary dict with chapters_ingested, chapters_skipped,
        chunks_created, entities_found, and errors.
    """
    from app.db.redis import get_redis_client
    from app.schemas.knowledge import KnowledgeIngest

    redis = await get_redis_client()

    # Acquire lock to prevent concurrent ingestion runs
    lock_val = await redis.cache_get(_LOCK_KEY)
    if lock_val:
        logger.info("Feynman ingestion already running — skipping")
        return {"status": "skipped", "reason": "Another ingestion is already running"}

    await redis.cache_set(_LOCK_KEY, "running", ttl=7200)  # 2-hour max lock

    cycle_start = _time.perf_counter()
    now = datetime.now(tz=timezone.utc)

    total_chapters = _get_total_chapters(volumes)
    results: dict[str, Any] = {
        "status": "ok",
        "timestamp": now.isoformat(),
        "volumes_requested": volumes or [1, 2, 3],
        "total_chapters": total_chapters,
        "chapters_ingested": 0,
        "chapters_skipped": 0,
        "chunks_created": 0,
        "entities_found": 0,
        "errors": [],
    }

    logger.info(
        "═══════════════════════════════════════════════════════════════"
    )
    logger.info(
        "FEYNMAN LECTURES INGESTION: starting (%d chapters across volumes %s)",
        total_chapters,
        volumes or [1, 2, 3],
    )
    logger.info(
        "═══════════════════════════════════════════════════════════════"
    )

    try:
        service, owner, db_ctx = await _build_knowledge_service()
    except Exception as exc:
        logger.exception("Failed to build KnowledgeService: %s", exc)
        await redis.cache_delete(_LOCK_KEY)
        return {
            "status": "error",
            "error": f"Failed to initialise KnowledgeService: {exc}",
        }

    # Use Gemini to synthesise comprehensive chapter summaries
    # (feynmanlectures.caltech.edu is behind Cloudflare, blocks automated access)
    from app.integrations.llm.factory import get_llm_client
    llm = get_llm_client("gemini")

    try:
        processed = 0

        for vol_num in sorted(FEYNMAN_VOLUMES.keys()):
            if volumes and vol_num not in volumes:
                continue

            vol_data = FEYNMAN_VOLUMES[vol_num]
            vol_prefix = vol_data["url_prefix"]
            vol_title = vol_data["title"]

            logger.info("── Volume %d: %s ──", vol_num, vol_title)

            for ch_num, ch_title in sorted(vol_data["chapters"].items()):
                processed += 1
                ingested_key = f"{_INGESTED_PREFIX}:{vol_num}_{ch_num}"

                # Skip already-ingested chapters
                already_done = await redis.cache_get(ingested_key)
                if already_done:
                    logger.debug(
                        "Skipping Vol %s Ch %d (%s) — already ingested",
                        vol_prefix, ch_num, ch_title,
                    )
                    results["chapters_skipped"] += 1

                    progress = {
                        "current_volume": vol_num,
                        "current_chapter": ch_num,
                        "processed": processed,
                        "total": total_chapters,
                        "percent": round(processed / total_chapters * 100, 1),
                        "status": "running",
                    }
                    await redis.cache_set(
                        _PROGRESS_KEY, json.dumps(progress), ttl=_METRICS_TTL,
                    )
                    continue

                full_title = f"Feynman Lectures Vol. {vol_num}, Chapter {ch_num}: {ch_title}"
                logger.info(
                    "[%d/%d] Synthesising: %s",
                    processed, total_chapters, full_title,
                )

                # Generate comprehensive chapter content via Gemini
                # (Gemini was trained on the Feynman Lectures and knows them deeply)
                try:
                    resp = await llm.chat_completion(
                        messages=[
                            {"role": "system", "content": (
                                "You are a physics professor writing comprehensive lecture notes. "
                                "Write detailed, technical content based on Feynman's Lectures on Physics. "
                                "Include key equations in LaTeX notation. Be thorough and precise — "
                                "this will be used as reference material for nanotechnology research. "
                                "Include specific derivations, physical intuitions, and Feynman's "
                                "unique insights where relevant."
                            )},
                            {"role": "user", "content": (
                                f"Write a comprehensive technical summary (800-1500 words) of "
                                f"'{full_title}' from The Feynman Lectures on Physics.\n\n"
                                f"Cover the key concepts, equations, derivations, and physical "
                                f"intuitions Feynman presents. Use LaTeX for equations. Be specific "
                                f"and technical — this is for a physics knowledge base, not a "
                                f"popular science summary."
                            )},
                        ],
                        model="gemini-3.1-pro-preview",
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    content = f"# {full_title}\n\n{resp['content'].strip()}"
                except Exception as exc:
                    error_msg = f"LLM synthesis failed for {full_title}: {exc}"
                    logger.warning(error_msg)
                    results["errors"].append(error_msg)
                    await asyncio.sleep(1.0)
                    continue

                if len(content) < 200:
                    error_msg = f"{full_title}: synthesised content too short"
                    logger.warning(error_msg)
                    results["errors"].append(error_msg)
                    continue

                # Ingest via KnowledgeService
                try:
                    ingest_data = KnowledgeIngest(
                        content=content,
                        source_type="document",
                        title=full_title,
                        metadata={
                            "source": "feynman_lectures",
                            "volume": vol_num,
                            "chapter": ch_num,
                            "chapter_title": ch_title,
                            "synthesis_method": "gemini_3.1_pro",
                            "auto_ingested": True,
                        },
                    )
                    response = await service.ingest(
                        user_id=owner.id, data=ingest_data,
                    )

                    chunks = response.chunk_count or 0
                    entities = response.entity_count or 0
                    results["chapters_ingested"] += 1
                    results["chunks_created"] += chunks
                    results["entities_found"] += entities

                    logger.info(
                        "  Ingested: %d chunks, %d entities",
                        chunks, entities,
                    )

                    # Mark as ingested in Redis (permanent)
                    await redis.cache_set(
                        ingested_key,
                        json.dumps({
                            "source_id": str(response.id),
                            "chunks": chunks,
                            "entities": entities,
                            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
                        }),
                        ttl=_METRICS_TTL,
                    )

                except Exception as exc:
                    error_msg = f"Ingestion failed for {full_title}: {exc}"
                    logger.exception(error_msg)
                    results["errors"].append(error_msg)

                # Update progress
                progress = {
                    "current_volume": vol_num,
                    "current_chapter": ch_num,
                    "current_title": ch_title,
                    "processed": processed,
                    "total": total_chapters,
                    "percent": round(processed / total_chapters * 100, 1),
                    "chapters_ingested": results["chapters_ingested"],
                    "chunks_created": results["chunks_created"],
                    "entities_found": results["entities_found"],
                    "status": "running",
                }
                await redis.cache_set(
                    _PROGRESS_KEY, json.dumps(progress), ttl=_METRICS_TTL,
                )

                # Rate-limit between LLM calls
                await asyncio.sleep(1.0)

    except Exception as exc:
        logger.exception("Feynman ingestion cycle failed: %s", exc)
        results["status"] = "error"
        results["errors"].append(f"Cycle failure: {exc}")
    finally:
        # Close the DB session
        try:
            await db_ctx.__aexit__(None, None, None)
        except Exception:
            pass

        # Release the lock
        await redis.cache_delete(_LOCK_KEY)

    elapsed = round(_time.perf_counter() - cycle_start, 1)
    results["elapsed_seconds"] = elapsed

    # Store final progress
    final_progress = {
        "status": "completed",
        "total": total_chapters,
        "processed": total_chapters,
        "percent": 100.0,
        "chapters_ingested": results["chapters_ingested"],
        "chapters_skipped": results["chapters_skipped"],
        "chunks_created": results["chunks_created"],
        "entities_found": results["entities_found"],
        "errors": len(results["errors"]),
        "elapsed_seconds": elapsed,
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    await redis.cache_set(
        _PROGRESS_KEY, json.dumps(final_progress), ttl=_METRICS_TTL,
    )

    logger.info(
        "═══════════════════════════════════════════════════════════════"
    )
    logger.info(
        "FEYNMAN LECTURES INGESTION: complete in %.1fs — "
        "%d ingested, %d skipped, %d chunks, %d entities, %d errors",
        elapsed,
        results["chapters_ingested"],
        results["chapters_skipped"],
        results["chunks_created"],
        results["entities_found"],
        len(results["errors"]),
    )
    logger.info(
        "═══════════════════════════════════════════════════════════════"
    )

    # Auto-chain: if we just finished a single volume, trigger the next
    if volumes and len(volumes) == 1:
        next_vol = volumes[0] + 1
        if next_vol in FEYNMAN_VOLUMES:
            import asyncio
            logger.info("Auto-chaining: triggering Feynman Vol %d ingestion", next_vol)
            asyncio.create_task(_chain_next_volume(next_vol))

    return results


async def _chain_next_volume(vol_num: int) -> None:
    """Auto-trigger ingestion of the next Feynman volume after a short delay."""
    import asyncio
    await asyncio.sleep(5)  # brief pause between volumes
    try:
        result = await ingest_feynman_lectures(volumes=[vol_num])
        logger.info(
            "Chained Feynman Vol %d: %d chapters ingested",
            vol_num, result.get("chapters_ingested", 0),
        )
    except Exception as exc:
        logger.warning("Chained Feynman Vol %d failed: %s", vol_num, exc)


async def get_ingestion_status() -> dict[str, Any]:
    """Return current Feynman Lectures ingestion progress.

    Reads from Redis to report:
      - Overall progress (percent, chapters done)
      - Per-volume breakdown of ingested chapters
      - Whether ingestion is currently running
    """
    from app.db.redis import get_redis_client

    redis = await get_redis_client()

    # Overall progress
    raw = await redis.cache_get(_PROGRESS_KEY)
    progress = json.loads(raw) if raw else None

    # Check if currently running
    lock_val = await redis.cache_get(_LOCK_KEY)
    is_running = lock_val is not None

    # Per-volume breakdown
    per_volume: dict[str, dict[str, Any]] = {}
    for vol_num, vol_data in FEYNMAN_VOLUMES.items():
        total_ch = len(vol_data["chapters"])
        ingested_ch = 0
        for ch_num in vol_data["chapters"]:
            key = f"{_INGESTED_PREFIX}:{vol_num}_{ch_num}"
            val = await redis.cache_get(key)
            if val:
                ingested_ch += 1
        per_volume[f"volume_{vol_num}"] = {
            "title": vol_data["title"],
            "total_chapters": total_ch,
            "ingested_chapters": ingested_ch,
            "percent": round(ingested_ch / total_ch * 100, 1) if total_ch else 0,
        }

    total_all = sum(v["total_chapters"] for v in per_volume.values())
    ingested_all = sum(v["ingested_chapters"] for v in per_volume.values())

    return {
        "is_running": is_running,
        "progress": progress,
        "overall": {
            "total_chapters": total_all,
            "ingested_chapters": ingested_all,
            "percent": round(ingested_all / total_all * 100, 1) if total_all else 0,
        },
        "per_volume": per_volume,
    }
