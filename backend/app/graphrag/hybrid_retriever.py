"""
Hybrid retriever for the JARVIS knowledge graph.

Combines **vector similarity** search (Qdrant) with **graph traversal**
(Neo4j) and merges the results via reciprocal rank fusion (RRF).  The
final output is a pre-formatted context string ready for injection into
an LLM prompt, together with structured metadata about matched sources
and entities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.graphrag.entity_extractor import Entity, EntityExtractor
from app.graphrag.graph_store import GraphStore
from app.graphrag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class RetrievalResult:
    """Container for a hybrid retrieval response."""

    context: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    graph_context: str = ""


# ---------------------------------------------------------------------------
# RRF constant (standard value from the literature)
# ---------------------------------------------------------------------------
_RRF_K = 60


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------


class HybridRetriever:
    """
    Orchestrates a multi-signal retrieval pipeline:

    1. **Entity extraction** — pull entities from the user query.
    2. **Vector search** — find the most semantically similar chunks.
    3. **Graph search** — traverse the knowledge graph from extracted entities.
    4. **Reciprocal rank fusion** — merge and re-rank both result sets.
    5. **Context formatting** — produce an LLM-ready context string.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        vector_store: VectorStore,
        entity_extractor: EntityExtractor,
    ) -> None:
        self._graph = graph_store
        self._vector = vector_store
        self._extractor = entity_extractor

    # ── Public API ──────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 10,
        use_graph: bool = True,
        use_vector: bool = True,
        min_score: float = 0.5,
    ) -> RetrievalResult:
        """
        Execute the full hybrid retrieval pipeline and return a
        :class:`RetrievalResult`.
        """

        # Step 1 — Extract entities from the query
        query_entities: list[Entity] = []
        if use_graph:
            try:
                query_entities = await self._extractor.extract_entities(query)
                logger.info(
                    "Extracted %d entities from query: %s",
                    len(query_entities),
                    [e.name for e in query_entities],
                )
            except Exception:
                logger.exception("Entity extraction failed; continuing without graph.")

        # Step 2 — Vector search
        vector_results: list[dict[str, Any]] = []
        if use_vector:
            try:
                filter_cond = (
                    {"user_id": user_id} if user_id else None
                )
                vector_results = await self._vector.search_similar(
                    query=query,
                    limit=top_k,
                    min_score=min_score,
                    filter_conditions=filter_cond,
                )
                logger.info(
                    "Vector search returned %d results.", len(vector_results)
                )
            except Exception:
                logger.exception("Vector search failed; continuing without vectors.")

        # Step 3 — Graph search
        graph_results: list[dict[str, Any]] = []
        graph_context_parts: list[str] = []
        if use_graph and query_entities:
            try:
                for entity in query_entities:
                    # Look up entity in the graph (exact + fuzzy)
                    found = await self._graph.get_entity(entity.name)
                    if found is None:
                        search_hits = await self._graph.search_entities(
                            entity.name, limit=3
                        )
                        if search_hits:
                            found = search_hits[0]

                    if found is not None:
                        # Get the neighbourhood context
                        ctx = await self._graph.get_entity_context(found.name)
                        graph_context_parts.append(ctx)

                        # Fetch neighbours for structured results
                        subgraph = await self._graph.get_neighbors(
                            found.name, depth=2
                        )
                        for ent in subgraph.get("entities", []):
                            graph_results.append(
                                {
                                    "type": "entity",
                                    "name": ent["name"],
                                    "entity_type": ent.get("type", "CONCEPT"),
                                    "text": ent.get("description", ""),
                                    "source": "graph",
                                }
                            )
                        for rel in subgraph.get("relationships", []):
                            graph_results.append(
                                {
                                    "type": "relationship",
                                    "text": (
                                        f"{rel['source']} --[{rel['type']}]--> "
                                        f"{rel['target']}"
                                        + (
                                            f": {rel['description']}"
                                            if rel.get("description")
                                            else ""
                                        )
                                    ),
                                    "source": "graph",
                                }
                            )
                logger.info(
                    "Graph search returned %d results.", len(graph_results)
                )
            except Exception:
                logger.exception("Graph search failed; continuing without graph.")

        # Step 4 — Combine and rank
        combined = await self._combine_results(vector_results, graph_results)
        combined = combined[:top_k]

        # Step 5 — Format context
        context = await self._format_context(combined)
        graph_context = "\n\n".join(graph_context_parts) if graph_context_parts else ""

        entity_dicts = [e.to_dict() for e in query_entities]

        return RetrievalResult(
            context=context,
            sources=combined,
            entities=entity_dicts,
            graph_context=graph_context,
        )

    # ── Reciprocal rank fusion ──────────────────────────────────────────

    async def _combine_results(
        self,
        vector_results: list[dict[str, Any]],
        graph_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Merge vector and graph results using reciprocal rank fusion.

        Each result is assigned a score of ``1 / (k + rank)`` per list it
        appears in.  Results appearing in both lists receive the sum of
        their per-list scores.  The final list is sorted by descending
        combined score, with duplicates removed.
        """
        scored: dict[str, dict[str, Any]] = {}

        # Score vector results
        for rank, item in enumerate(vector_results):
            key = self._result_key(item)
            rrf_score = 1.0 / (_RRF_K + rank + 1)
            if key in scored:
                scored[key]["rrf_score"] += rrf_score
            else:
                scored[key] = {
                    **item,
                    "rrf_score": rrf_score,
                    "origin": "vector",
                }

        # Score graph results
        for rank, item in enumerate(graph_results):
            key = self._result_key(item)
            rrf_score = 1.0 / (_RRF_K + rank + 1)
            if key in scored:
                scored[key]["rrf_score"] += rrf_score
                scored[key]["origin"] = "hybrid"
            else:
                scored[key] = {
                    **item,
                    "rrf_score": rrf_score,
                    "origin": "graph",
                }

        # Sort by descending RRF score
        ranked = sorted(
            scored.values(), key=lambda x: x.get("rrf_score", 0), reverse=True
        )
        return ranked

    @staticmethod
    def _result_key(item: dict[str, Any]) -> str:
        """Derive a deduplication key from a result dict."""
        if item.get("id"):
            return str(item["id"])
        if item.get("chunk_id"):
            return str(item["chunk_id"])
        if item.get("name"):
            return f"entity:{item['name']}"
        # Fall back to a content hash
        text = item.get("text", "")
        return f"text:{hash(text)}"

    # ── Context formatting ──────────────────────────────────────────────

    async def _format_context(
        self,
        results: list[dict[str, Any]],
    ) -> str:
        """
        Convert the ranked result list into a structured plain-text context
        string for LLM consumption.
        """
        if not results:
            return "No relevant information found in the knowledge base."

        sections: list[str] = []
        sections.append("=== KNOWLEDGE CONTEXT ===\n")

        # Group by origin
        vector_items = [
            r for r in results if r.get("origin") in ("vector", "hybrid")
        ]
        graph_items = [
            r for r in results if r.get("origin") in ("graph", "hybrid")
        ]

        if vector_items:
            sections.append("--- Document Chunks ---")
            for i, item in enumerate(vector_items, 1):
                text = item.get("text", "").strip()
                score = item.get("score") or item.get("rrf_score", 0)
                source_id = item.get("source_id", "unknown")
                if text:
                    sections.append(
                        f"[{i}] (score: {score:.3f}, source: {source_id})\n{text}\n"
                    )

        if graph_items:
            sections.append("--- Knowledge Graph ---")
            for i, item in enumerate(graph_items, 1):
                if item.get("type") == "entity":
                    sections.append(
                        f"Entity: {item.get('name', '?')} "
                        f"({item.get('entity_type', 'CONCEPT')})"
                        + (f" — {item['text']}" if item.get("text") else "")
                    )
                elif item.get("type") == "relationship":
                    sections.append(f"Relation: {item.get('text', '')}")
                else:
                    text = item.get("text", "").strip()
                    if text:
                        sections.append(f"[G{i}] {text}")

        sections.append("\n=== END CONTEXT ===")
        return "\n".join(sections)
