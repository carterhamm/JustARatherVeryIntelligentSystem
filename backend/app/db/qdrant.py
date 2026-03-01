"""
Qdrant async client wrapper for the JARVIS vector store.

Manages a ``QdrantAsyncClient`` instance, auto-creates the target
collection (1536-dim, cosine distance — compatible with OpenAI
``text-embedding-3-small``), and exposes simple CRUD + search helpers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton holder
# ---------------------------------------------------------------------------
_store: Optional["QdrantStore"] = None

# Default vector size for OpenAI text-embedding-3-small
_DEFAULT_VECTOR_SIZE = 1536


class QdrantStore:
    """Async wrapper around the Qdrant vector database."""

    def __init__(
        self,
        url: str,
        collection_name: str = "jarvis_knowledge",
        api_key: Optional[str] = None,
        vector_size: int = _DEFAULT_VECTOR_SIZE,
    ) -> None:
        self._url = url
        self._collection_name = collection_name
        self._api_key = api_key
        self._vector_size = vector_size
        self._client: Optional[AsyncQdrantClient] = None

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self) -> None:
        """
        Create the async Qdrant client and ensure the target collection
        exists (creating it with cosine distance if it does not).
        """
        self._client = AsyncQdrantClient(
            url=self._url,
            api_key=self._api_key,
            timeout=30,
        )

        try:
            collection_info = await self._client.get_collection(
                self._collection_name
            )
            logger.info(
                "Qdrant collection '%s' already exists (%d points).",
                self._collection_name,
                collection_info.points_count or 0,
            )
        except (UnexpectedResponse, Exception):
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d, cosine).",
                self._collection_name,
                self._vector_size,
            )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _ensure_client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError(
                "QdrantStore is not initialised. Call initialize() first."
            )
        return self._client

    # -- write operations ----------------------------------------------------

    async def upsert(
        self,
        id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> None:
        """Insert or update a single point in the collection."""
        client = self._ensure_client()
        point = PointStruct(
            id=id,
            vector=vector,
            payload=payload,
        )
        await client.upsert(
            collection_name=self._collection_name,
            points=[point],
        )

    async def upsert_batch(
        self,
        points: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> None:
        """
        Batch-upsert a list of point dicts.

        Each dict must contain ``id``, ``vector``, and ``payload`` keys.
        """
        client = self._ensure_client()
        structs = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        for i in range(0, len(structs), batch_size):
            batch = structs[i : i + batch_size]
            await client.upsert(
                collection_name=self._collection_name,
                points=batch,
            )

    # -- search --------------------------------------------------------------

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        filter_conditions: Optional[dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """
        Perform a nearest-neighbour search.

        ``filter_conditions`` is a simple ``{field: value}`` mapping that is
        translated to Qdrant ``must`` match filters.

        Returns a list of dicts with ``id``, ``score``, and ``payload``.
        """
        client = self._ensure_client()

        qdrant_filter: Optional[Filter] = None
        if filter_conditions:
            must_clauses = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_conditions.items()
            ]
            qdrant_filter = Filter(must=must_clauses)

        results = await client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            score_threshold=score_threshold,
        )

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "payload": hit.payload or {},
            }
            for hit in results
        ]

    # -- point-level CRUD ---------------------------------------------------

    async def get_by_id(self, id: str) -> Optional[dict[str, Any]]:
        """Retrieve a single point by its ID, or ``None`` if missing."""
        client = self._ensure_client()
        try:
            points = await client.retrieve(
                collection_name=self._collection_name,
                ids=[id],
                with_vectors=True,
                with_payload=True,
            )
            if not points:
                return None
            p = points[0]
            return {
                "id": str(p.id),
                "vector": p.vector,
                "payload": p.payload or {},
            }
        except Exception:
            logger.exception("Failed to retrieve point %s", id)
            return None

    async def delete(self, ids: list[str]) -> None:
        """Delete one or more points by ID."""
        client = self._ensure_client()
        await client.delete(
            collection_name=self._collection_name,
            points_selector=PointIdsList(points=ids),
        )

    async def count(self) -> int:
        """Return the number of points in the collection."""
        client = self._ensure_client()
        info = await client.get_collection(self._collection_name)
        return info.points_count or 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_qdrant_store() -> QdrantStore:
    """
    Return the module-level singleton ``QdrantStore``.

    Settings are loaded lazily from ``app.config.settings``.
    The caller must still ``await store.initialize()`` before use.
    """
    global _store
    if _store is None:
        from app.config import settings

        _store = QdrantStore(
            url=settings.QDRANT_URL,
            collection_name=getattr(
                settings, "QDRANT_COLLECTION", "jarvis_knowledge"
            ),
            api_key=getattr(settings, "QDRANT_API_KEY", None),
        )
    return _store


async def close_qdrant_store() -> None:
    """Shut down the singleton store (call during app shutdown)."""
    global _store
    if _store is not None:
        await _store.close()
        _store = None
