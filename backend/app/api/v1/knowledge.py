"""
Knowledge-base API router for the JARVIS assistant.

Provides endpoints for ingesting content, searching the knowledge base
(vector + graph hybrid retrieval), managing sources, and inspecting the
knowledge graph.

All endpoints require authentication via the ``current_user`` dependency.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.neo4j import get_neo4j_client
from app.db.qdrant import get_qdrant_store
from app.graphrag.entity_extractor import EntityExtractor
from app.graphrag.graph_store import GraphStore
from app.graphrag.hybrid_retriever import HybridRetriever
from app.graphrag.vector_store import VectorStore
from app.schemas.knowledge import (
    EntityResponse,
    GraphNeighborhoodResponse,
    KnowledgeIngest,
    KnowledgeResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    RelationshipResponse,
)
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


async def _build_knowledge_service(
    db: AsyncSession = Depends(get_db),
) -> KnowledgeService:
    """
    Construct a :class:`KnowledgeService` with all required dependencies.

    Uses Gemini for embeddings and entity extraction (free with existing API key).
    """
    # -- infrastructure clients --
    neo4j_client = get_neo4j_client()
    qdrant_store = get_qdrant_store()

    # -- graphrag components (all use Gemini now, no OpenAI needed) --
    entity_extractor = EntityExtractor()
    graph_store = GraphStore(neo4j_client=neo4j_client)
    vector_store = VectorStore(qdrant_store=qdrant_store)
    hybrid_retriever = HybridRetriever(
        graph_store=graph_store,
        vector_store=vector_store,
        entity_extractor=entity_extractor,
    )

    return KnowledgeService(
        db=db,
        hybrid_retriever=hybrid_retriever,
        entity_extractor=entity_extractor,
        graph_store=graph_store,
        vector_store=vector_store,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/ingest",
    response_model=KnowledgeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest content into the knowledge base",
)
async def ingest_knowledge(
    data: KnowledgeIngest,
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> KnowledgeResponse:
    """
    Ingest a piece of text (or document content) into the JARVIS knowledge
    base.  The content is automatically chunked, entities are extracted via
    LLM, and everything is stored in both the graph and vector databases.
    """
    try:
        result = await service.ingest(user_id=current_user.id, data=data)
        return result
    except Exception as exc:
        logger.exception("Knowledge ingestion failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc


@router.get(
    "/search",
    response_model=KnowledgeSearchResponse,
    summary="Search knowledge base (GET)",
)
async def search_knowledge_get(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(5, ge=1, le=50),
    use_graph: bool = Query(True),
    use_vector: bool = Query(True),
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> KnowledgeSearchResponse:
    """Search the knowledge base using query parameters."""
    request = KnowledgeSearchRequest(
        query=query,
        limit=limit,
        use_graph=use_graph,
        use_vector=use_vector,
    )
    try:
        return await service.search(user_id=current_user.id, request=request)
    except Exception as exc:
        logger.exception("Knowledge search failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        ) from exc


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    summary="Search knowledge base (POST)",
)
async def search_knowledge_post(
    request: KnowledgeSearchRequest,
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> KnowledgeSearchResponse:
    """Search the knowledge base with full options via request body."""
    try:
        return await service.search(user_id=current_user.id, request=request)
    except Exception as exc:
        logger.exception("Knowledge search failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        ) from exc


@router.get(
    "/sources",
    response_model=list[KnowledgeResponse],
    summary="List ingested knowledge sources",
)
async def list_sources(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> list[KnowledgeResponse]:
    """Return a paginated list of knowledge sources for the current user."""
    return await service.list_sources(
        user_id=current_user.id, skip=skip, limit=limit
    )


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge source",
)
async def delete_source(
    source_id: uuid.UUID,
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> None:
    """
    Delete a knowledge source and all of its associated graph entities
    and vector embeddings.
    """
    deleted = await service.delete_source(
        user_id=current_user.id, source_id=source_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge source not found.",
        )


@router.get(
    "/entities",
    response_model=list[EntityResponse],
    summary="List extracted entities",
)
async def list_entities(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> list[EntityResponse]:
    """Return a paginated list of entities in the knowledge graph."""
    return await service.get_entities(
        user_id=current_user.id, skip=skip, limit=limit
    )


@router.get(
    "/graph/{entity_name}",
    response_model=GraphNeighborhoodResponse,
    summary="Get entity graph neighbourhood",
)
async def get_entity_graph(
    entity_name: str,
    depth: int = Query(2, ge=1, le=5),
    current_user: Any = Depends(get_current_active_user),
    service: KnowledgeService = Depends(_build_knowledge_service),
) -> GraphNeighborhoodResponse:
    """
    Return the sub-graph (entities and relationships) surrounding a named
    entity, traversed up to *depth* hops.
    """
    graph_store = service._graph

    # Verify entity exists
    entity = await graph_store.get_entity(entity_name)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_name}' not found in the knowledge graph.",
        )

    subgraph = await graph_store.get_neighbors(entity_name, depth=depth)

    entity_response = EntityResponse(
        name=entity.name,
        type=entity.type,
        description=entity.description,
        properties=entity.properties,
    )

    entities = [
        EntityResponse(
            name=e["name"],
            type=e.get("type", "CONCEPT"),
            description=e.get("description"),
            properties=e.get("properties", {}),
        )
        for e in subgraph.get("entities", [])
    ]

    relationships = [
        RelationshipResponse(
            source=r["source"],
            target=r["target"],
            type=r.get("type", "RELATED_TO"),
            description=r.get("description"),
            weight=r.get("weight", 1.0),
        )
        for r in subgraph.get("relationships", [])
    ]

    return GraphNeighborhoodResponse(
        entity=entity_response,
        entities=entities,
        relationships=relationships,
    )
