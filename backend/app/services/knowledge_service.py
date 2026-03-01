"""
Knowledge ingestion and retrieval service for JARVIS.

Orchestrates the full lifecycle: text chunking, entity extraction, graph
population, vector embedding, and hybrid search — all via a single
cohesive service class.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional, Sequence

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.graphrag.entity_extractor import Entity, EntityExtractor, Relationship
from app.graphrag.graph_store import GraphStore
from app.graphrag.hybrid_retriever import HybridRetriever
from app.graphrag.vector_store import VectorStore
from app.models.knowledge import KnowledgeSource
from app.schemas.knowledge import (
    KnowledgeIngest,
    KnowledgeResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    EntityResponse,
    RelationshipResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CHUNK_SIZE = 500  # target tokens (approx 4 chars per token)
_CHARS_PER_TOKEN = 4


class KnowledgeService:
    """
    High-level service that ties together the database, graph store,
    vector store, entity extractor, and hybrid retriever.
    """

    def __init__(
        self,
        db: AsyncSession,
        hybrid_retriever: HybridRetriever,
        entity_extractor: EntityExtractor,
        graph_store: GraphStore,
        vector_store: VectorStore,
    ) -> None:
        self._db = db
        self._retriever = hybrid_retriever
        self._extractor = entity_extractor
        self._graph = graph_store
        self._vector = vector_store

    # ── Ingestion ───────────────────────────────────────────────────────

    async def ingest(
        self,
        user_id: uuid.UUID,
        data: KnowledgeIngest,
    ) -> KnowledgeResponse:
        """
        Ingest a piece of content into the JARVIS knowledge base.

        1. Persist the source record (status ``pending``).
        2. Chunk the text.
        3. Extract entities and relationships via the LLM.
        4. Store entities/relationships in Neo4j.
        5. Store chunk embeddings in Qdrant.
        6. Update the source record (status ``completed``).
        """
        # -- 1. Create source record ----------------------------------------
        source = KnowledgeSource(
            id=uuid.uuid4(),
            user_id=user_id,
            source_type=data.source_type,
            title=data.title or self._derive_title(data.content),
            content=data.content,
            status="pending",
            metadata_=data.metadata,
        )
        self._db.add(source)
        await self._db.flush()

        try:
            # Mark as processing
            source.status = "processing"
            await self._db.flush()

            # -- 2. Chunk text -----------------------------------------------
            chunks = self._chunk_text(data.content, chunk_size=_DEFAULT_CHUNK_SIZE)
            source.chunk_count = len(chunks)

            # -- 3. Extract entities and relationships -----------------------
            all_entities: list[Entity] = []
            all_relationships: list[Relationship] = []

            # Extract from the full text (or from each chunk for very long docs)
            if len(data.content) < 8000:
                entities, relationships = await self._extractor.extract_all(
                    data.content
                )
                all_entities.extend(entities)
                all_relationships.extend(relationships)
            else:
                for chunk in chunks:
                    entities, relationships = await self._extractor.extract_all(
                        chunk
                    )
                    all_entities.extend(entities)
                    all_relationships.extend(relationships)

            # Deduplicate entities by name
            seen_names: set[str] = set()
            unique_entities: list[Entity] = []
            for ent in all_entities:
                if ent.name not in seen_names:
                    seen_names.add(ent.name)
                    unique_entities.append(ent)
            all_entities = unique_entities

            source.entity_count = len(all_entities)

            # -- 4. Store in graph -------------------------------------------
            user_id_str = str(user_id)
            for entity in all_entities:
                entity.properties["source_id"] = str(source.id)
                await self._graph.add_entity(entity, user_id=user_id_str)

            for rel in all_relationships:
                await self._graph.add_relationship(rel, user_id=user_id_str)

            # -- 5. Store chunks in vector store -----------------------------
            chunk_dicts = []
            for idx, chunk_text in enumerate(chunks):
                chunk_id = VectorStore.make_chunk_id(str(source.id), idx)
                chunk_dicts.append(
                    {
                        "id": chunk_id,
                        "text": chunk_text,
                        "source": str(source.id),
                        "metadata": {
                            "user_id": user_id_str,
                            "source_type": data.source_type,
                            "title": source.title or "",
                            "chunk_index": idx,
                        },
                    }
                )

            if chunk_dicts:
                await self._vector.add_chunks_batch(chunk_dicts)

            # -- 6. Mark complete --------------------------------------------
            source.status = "completed"
            await self._db.commit()

            logger.info(
                "Ingested source %s: %d chunks, %d entities, %d relationships.",
                source.id,
                len(chunks),
                len(all_entities),
                len(all_relationships),
            )

        except Exception:
            logger.exception("Ingestion failed for source %s.", source.id)
            source.status = "failed"
            await self._db.commit()
            raise

        return KnowledgeResponse.model_validate(source)

    # ── Search ─────────────────────────────────────────────────────────

    async def search(
        self,
        user_id: uuid.UUID,
        request: KnowledgeSearchRequest,
    ) -> KnowledgeSearchResponse:
        """
        Search the knowledge base using the hybrid retriever.
        """
        result = await self._retriever.retrieve(
            query=request.query,
            user_id=str(user_id),
            top_k=request.limit,
            use_graph=request.use_graph,
            use_vector=request.use_vector,
        )

        entity_responses = [
            EntityResponse(
                name=e.get("name", ""),
                type=e.get("type", "CONCEPT"),
                description=e.get("description"),
                properties=e.get("properties", {}),
            )
            for e in result.entities
        ]

        return KnowledgeSearchResponse(
            results=result.sources,
            context=result.context,
            entities=entity_responses,
            graph_context=result.graph_context or None,
        )

    # ── Source CRUD ────────────────────────────────────────────────────

    async def list_sources(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[KnowledgeResponse]:
        """List ingested knowledge sources for a user."""
        stmt = (
            select(KnowledgeSource)
            .where(KnowledgeSource.user_id == user_id)
            .order_by(KnowledgeSource.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return [KnowledgeResponse.model_validate(r) for r in rows]

    async def delete_source(
        self,
        user_id: uuid.UUID,
        source_id: uuid.UUID,
    ) -> bool:
        """
        Delete a knowledge source and its associated graph/vector data.

        Returns ``True`` if the source was found and deleted.
        """
        stmt = select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.user_id == user_id,
        )
        result = await self._db.execute(stmt)
        source = result.scalar_one_or_none()
        if source is None:
            return False

        # Remove from vector store
        try:
            await self._vector.delete_by_source(str(source_id))
        except Exception:
            logger.exception("Failed to delete vectors for source %s.", source_id)

        # Remove from graph store
        try:
            await self._graph.delete_entities_by_source(str(source_id))
        except Exception:
            logger.exception("Failed to delete graph entities for source %s.", source_id)

        # Remove from database
        await self._db.delete(source)
        await self._db.commit()

        logger.info("Deleted knowledge source %s.", source_id)
        return True

    # ── Entity listing ──────────────────────────────────────────────────

    async def get_entities(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[EntityResponse]:
        """
        List entities belonging to a user from the graph store.

        Queries Neo4j directly since entities are not stored in PostgreSQL.
        """
        from app.db.neo4j import Neo4jClient

        neo4j: Neo4jClient = self._graph._db  # noqa: access internal for query
        query = (
            "MATCH (e:Entity {user_id: $user_id}) "
            "RETURN e.name AS name, e.type AS type, "
            "       e.description AS description, "
            "       e.properties AS properties "
            "ORDER BY e.name "
            "SKIP $skip LIMIT $limit"
        )
        rows = await neo4j.execute_query(
            query,
            {"user_id": str(user_id), "skip": skip, "limit": limit},
        )
        return [
            EntityResponse(
                name=r["name"],
                type=r.get("type", "CONCEPT"),
                description=r.get("description"),
                properties=r.get("properties") or {},
            )
            for r in rows
        ]

    # ── Text chunking ──────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(
        text: str,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        overlap: int = 50,
    ) -> list[str]:
        """
        Split *text* into chunks of approximately *chunk_size* tokens.

        The strategy:
        1. Split on paragraph boundaries (double newline).
        2. Greedily merge consecutive paragraphs until the target size
           is reached.
        3. Apply a token-level overlap between adjacent chunks so
           important sentences at boundaries are not lost.
        """
        char_limit = chunk_size * _CHARS_PER_TOKEN
        overlap_chars = overlap * _CHARS_PER_TOKEN

        # Split on double newlines, preserving single newlines
        paragraphs = re.split(r"\n\s*\n", text.strip())
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return [text.strip()] if text.strip() else []

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)

            # If a single paragraph exceeds the limit, force-split it
            if para_len > char_limit:
                # Flush current buffer first
                if current:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_len = 0

                # Hard split on sentence boundaries
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sub_chunk: list[str] = []
                sub_len = 0
                for sentence in sentences:
                    if sub_len + len(sentence) > char_limit and sub_chunk:
                        chunks.append(" ".join(sub_chunk))
                        # Keep overlap
                        overlap_text = " ".join(sub_chunk)[-overlap_chars:]
                        sub_chunk = [overlap_text, sentence] if overlap_text else [sentence]
                        sub_len = sum(len(s) for s in sub_chunk)
                    else:
                        sub_chunk.append(sentence)
                        sub_len += len(sentence)
                if sub_chunk:
                    chunks.append(" ".join(sub_chunk))
                continue

            if current_len + para_len > char_limit and current:
                chunk_text = "\n\n".join(current)
                chunks.append(chunk_text)

                # Overlap: carry the tail of the previous chunk
                if overlap_chars > 0 and len(chunk_text) > overlap_chars:
                    tail = chunk_text[-overlap_chars:]
                    current = [tail, para]
                    current_len = len(tail) + para_len
                else:
                    current = [para]
                    current_len = para_len
            else:
                current.append(para)
                current_len += para_len

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    @staticmethod
    def _derive_title(content: str, max_len: int = 80) -> str:
        """Derive a title from the first line of content."""
        first_line = content.strip().split("\n")[0].strip()
        if len(first_line) > max_len:
            return first_line[: max_len - 3] + "..."
        return first_line
