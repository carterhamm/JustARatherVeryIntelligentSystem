"""
Pydantic v2 schemas for the JARVIS knowledge graph API.

Covers ingestion requests, search queries, and response envelopes for
entities, relationships, and knowledge sources.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class KnowledgeIngest(BaseModel):
    """Payload for the POST /knowledge/ingest endpoint."""

    content: str = Field(
        ...,
        min_length=1,
        description="Raw text content to ingest into the knowledge base.",
    )
    source_type: str = Field(
        default="text",
        description='Source type: "text", "document", "url", "email", or "message".',
    )
    title: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Human-readable title for the source.",
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Arbitrary metadata to store alongside the source.",
    )


class KnowledgeResponse(BaseModel):
    """Returned after a successful ingestion or when listing sources."""

    id: uuid.UUID
    source_type: str
    title: Optional[str] = None
    chunk_count: int = 0
    entity_count: int = 0
    status: str = "pending"
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class KnowledgeSearchRequest(BaseModel):
    """Body payload for POST /knowledge/search."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language query to search the knowledge base.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of results to return.",
    )
    use_graph: bool = Field(
        default=True,
        description="Include graph-based (entity / relationship) results.",
    )
    use_vector: bool = Field(
        default=True,
        description="Include vector-similarity results.",
    )


class KnowledgeSearchResponse(BaseModel):
    """Envelope returned by both GET and POST search endpoints."""

    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ranked list of matching knowledge chunks.",
    )
    context: str = Field(
        default="",
        description="Pre-formatted context string suitable for LLM prompts.",
    )
    entities: list["EntityResponse"] = Field(
        default_factory=list,
        description="Entities extracted or matched during retrieval.",
    )
    graph_context: Optional[str] = Field(
        default=None,
        description="Formatted graph neighbourhood context, if available.",
    )


# ---------------------------------------------------------------------------
# Entities & Relationships
# ---------------------------------------------------------------------------

class EntityResponse(BaseModel):
    """Public representation of a knowledge-graph entity."""

    name: str
    type: str
    description: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)


class RelationshipResponse(BaseModel):
    """Public representation of a knowledge-graph relationship."""

    source: str
    target: str
    type: str
    description: Optional[str] = None
    weight: float = 1.0


class GraphNeighborhoodResponse(BaseModel):
    """Subgraph returned by the /graph/{entity_name} endpoint."""

    entity: Optional[EntityResponse] = None
    entities: list[EntityResponse] = Field(default_factory=list)
    relationships: list[RelationshipResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Forward-ref resolution
# ---------------------------------------------------------------------------

KnowledgeSearchResponse.model_rebuild()
