"""
Qdrant-backed vector store for the JARVIS knowledge graph.

Wraps :class:`app.db.qdrant.QdrantStore` with automatic OpenAI embedding
generation (``text-embedding-3-small``) and a convenient document / chunk
ingestion API.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from openai import AsyncOpenAI

from app.db.qdrant import QdrantStore

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536  # dimensions for text-embedding-3-small


class VectorStore:
    """High-level vector store with integrated embedding generation."""

    def __init__(
        self,
        qdrant_store: QdrantStore,
        embedding_client: Optional[AsyncOpenAI] = None,
        embedding_model: str = _EMBEDDING_MODEL,
    ) -> None:
        self._qdrant = qdrant_store
        self._model = embedding_model
        self._oai: Optional[AsyncOpenAI] = embedding_client

    def _get_openai(self) -> AsyncOpenAI:
        """Lazy-initialise the embedding client if not injected."""
        if self._oai is None:
            self._oai = AsyncOpenAI(api_key="")  # TODO: swap to non-OpenAI embedding provider
        return self._oai

    # ── Embedding ───────────────────────────────────────────────────────

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate an embedding vector for *text* using OpenAI
        ``text-embedding-3-small``.

        Returns a list of 1536 floats.
        """
        client = self._get_openai()
        # Truncate very long texts to stay within token limits (~8191 tokens)
        # A rough heuristic: 1 token ~ 4 chars
        max_chars = 8191 * 4
        truncated = text[:max_chars] if len(text) > max_chars else text

        response = await client.embeddings.create(
            model=self._model,
            input=truncated,
        )
        return response.data[0].embedding

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed multiple texts in a single API call."""
        client = self._get_openai()
        max_chars = 8191 * 4
        truncated = [t[:max_chars] for t in texts]

        response = await client.embeddings.create(
            model=self._model,
            input=truncated,
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in sorted_data]

    # ── Document / chunk CRUD ──────────────────────────────────────────

    async def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Embed *text* and upsert a single document point into Qdrant.

        ``metadata`` is stored as the Qdrant payload alongside the text
        itself (under the key ``"text"``).
        """
        vector = await self.embed_text(text)
        payload = {**metadata, "text": text, "doc_id": doc_id}
        await self._qdrant.upsert(id=doc_id, vector=vector, payload=payload)

    async def add_chunk(
        self,
        chunk_id: str,
        text: str,
        source: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Embed a document chunk and store it with provenance information.

        ``source`` is the knowledge-source ID the chunk originated from.
        """
        vector = await self.embed_text(text)
        payload = {
            **metadata,
            "text": text,
            "chunk_id": chunk_id,
            "source_id": source,
        }
        await self._qdrant.upsert(id=chunk_id, vector=vector, payload=payload)

    async def add_chunks_batch(
        self,
        chunks: list[dict[str, Any]],
    ) -> None:
        """
        Batch-embed and upsert multiple chunks efficiently.

        Each dict in *chunks* must contain ``id``, ``text``, ``source``,
        and ``metadata`` keys.
        """
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        vectors = await self.embed_texts(texts)

        points = []
        for chunk, vector in zip(chunks, vectors):
            payload = {
                **chunk.get("metadata", {}),
                "text": chunk["text"],
                "chunk_id": chunk["id"],
                "source_id": chunk["source"],
            }
            points.append(
                {"id": chunk["id"], "vector": vector, "payload": payload}
            )

        await self._qdrant.upsert_batch(points)

    async def delete_document(self, doc_id: str) -> None:
        """Delete a single point by its document ID."""
        await self._qdrant.delete([doc_id])

    async def delete_by_source(self, source_id: str) -> None:
        """
        Delete all chunks belonging to a given knowledge source.

        Because Qdrant filtering requires a search-then-delete pattern for
        payload-based deletes, this scrolls through matching points and
        removes them in batches.
        """
        # Generate a dummy vector (all zeros) — we rely on filtering, not NN
        dummy_vector = [0.0] * _EMBEDDING_DIM
        batch_size = 100

        while True:
            results = await self._qdrant.search(
                query_vector=dummy_vector,
                limit=batch_size,
                filter_conditions={"source_id": source_id},
                score_threshold=None,
            )
            if not results:
                break
            ids = [r["id"] for r in results]
            await self._qdrant.delete(ids)
            if len(results) < batch_size:
                break

    # ── Search ─────────────────────────────────────────────────────────

    async def search_similar(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.7,
        filter_conditions: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Embed *query* and perform a nearest-neighbour search on Qdrant.

        Returns a list of dicts, each containing ``id``, ``score``,
        ``text``, and the full ``payload``.
        """
        vector = await self.embed_text(query)
        results = await self._qdrant.search(
            query_vector=vector,
            limit=limit,
            filter_conditions=filter_conditions,
            score_threshold=min_score,
        )
        enriched: list[dict[str, Any]] = []
        for r in results:
            enriched.append(
                {
                    "id": r["id"],
                    "score": r["score"],
                    "text": r["payload"].get("text", ""),
                    "source_id": r["payload"].get("source_id"),
                    "chunk_id": r["payload"].get("chunk_id"),
                    "payload": r["payload"],
                }
            )
        return enriched

    # ── Utilities ──────────────────────────────────────────────────────

    @staticmethod
    def make_chunk_id(source_id: str, chunk_index: int) -> str:
        """
        Deterministic chunk ID derived from the source ID and chunk index.

        Uses a truncated SHA-256 so the ID is Qdrant-friendly (no special
        characters, fixed length).
        """
        raw = f"{source_id}::{chunk_index}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
