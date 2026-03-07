"""
Retriever agent node for the J.A.R.V.I.S. orchestrator.

Executes a hybrid search (vector + graph) against the knowledge base
using the query extracted from the planner's output, then formats the
results into a textual context string consumed by downstream nodes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.state import AgentState
from app.db.qdrant import QdrantStore, get_qdrant_store
from app.integrations.llm_client import LLMClient
from app.config import settings

logger = logging.getLogger("jarvis.agents.retriever")

# Maximum number of chunks to include in retrieved context
_TOP_K = 6

# Minimum relevance score to keep a result
_SCORE_THRESHOLD = 0.55


async def retriever_node(state: AgentState) -> dict[str, Any]:
    """Search the knowledge base and return retrieved context.

    The search query is taken from the planner's ``search_query`` field.
    If absent, the last user message is used verbatim.

    Returns a partial state update with ``retrieved_context``.
    """
    # 1. Determine search query --------------------------------------------
    plan: dict[str, Any] = {}
    try:
        plan = json.loads(state.get("current_plan", "{}"))
    except json.JSONDecodeError:
        pass

    search_query = plan.get("search_query", "")
    if not search_query:
        # Fall back to the latest user message
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                search_query = msg.get("content", "")
                break

    if not search_query:
        logger.warning("Retriever invoked with no query; returning empty context.")
        return {"retrieved_context": ""}

    # 2. Generate query embedding ------------------------------------------
    try:
        embedding = await _embed_query(search_query)
    except Exception as exc:
        logger.exception("Failed to generate query embedding: %s", exc)
        return {
            "retrieved_context": "",
            "error": f"Embedding generation failed: {exc}",
        }

    # 3. Vector search (Qdrant) --------------------------------------------
    results: list[dict[str, Any]] = []
    try:
        store: QdrantStore = get_qdrant_store()
        user_id = state.get("user_id", "")
        filter_conditions = {"user_id": user_id} if user_id else None

        results = await store.search(
            query_vector=embedding,
            limit=_TOP_K,
            filter_conditions=filter_conditions,
            score_threshold=_SCORE_THRESHOLD,
        )
        logger.info(
            "Qdrant returned %d results for query: '%s'",
            len(results),
            search_query[:80],
        )
    except Exception as exc:
        logger.exception("Qdrant search failed: %s", exc)
        # Non-fatal — we still try to respond

    # 4. Format context string ---------------------------------------------
    context_parts: list[str] = []
    for i, hit in enumerate(results, start=1):
        payload = hit.get("payload", {})
        score = hit.get("score", 0.0)
        title = payload.get("title", "Untitled")
        text = payload.get("text", payload.get("content", ""))
        source_type = payload.get("source_type", "unknown")
        context_parts.append(
            f"[Source {i}] (type={source_type}, relevance={score:.2f}) "
            f"{title}\n{text}"
        )

    retrieved_context = "\n\n---\n\n".join(context_parts) if context_parts else ""

    return {"retrieved_context": retrieved_context}


# ── Helpers ──────────────────────────────────────────────────────────────

async def _embed_query(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key="")  # TODO: swap to non-OpenAI embedding provider
    response = await client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
    )
    return response.data[0].embedding
