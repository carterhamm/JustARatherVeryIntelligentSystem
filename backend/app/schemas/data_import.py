"""
Pydantic v2 schemas for the J.A.R.V.I.S. data import pipeline.

Covers text, file, URL, and batch imports into the knowledge base.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ═════════════════════════════════════════════════════════════════════════
# Request schemas
# ═════════════════════════════════════════════════════════════════════════

class ImportTextRequest(BaseModel):
    """Import raw text content into the knowledge base."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(
        ...,
        min_length=1,
        description="The raw text content to ingest.",
    )
    title: Optional[str] = Field(
        None,
        max_length=512,
        description="Optional title for this content.",
    )
    source_type: Optional[str] = Field(
        "text",
        description='Content type hint: "text", "note", "snippet", etc.',
    )


class ImportURLRequest(BaseModel):
    """Import content from a web URL."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        ...,
        min_length=1,
        description="The URL to fetch and import.",
    )


class ImportBatchItem(BaseModel):
    """A single item within a batch import request."""

    type: str = Field(
        ...,
        description='Item type: "text", "url", "email", "message".',
    )
    content: Optional[str] = Field(
        None,
        description="Raw text content (for type=text or type=message).",
    )
    url: Optional[str] = Field(
        None,
        description="URL to fetch (for type=url).",
    )
    title: Optional[str] = Field(None, max_length=512)
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Arbitrary metadata to attach to the ingested source.",
    )


class ImportBatchRequest(BaseModel):
    """Batch import multiple items at once."""

    model_config = ConfigDict(extra="forbid")

    items: list[ImportBatchItem] = Field(
        ...,
        min_length=1,
        description="List of items to import.",
    )


# ═════════════════════════════════════════════════════════════════════════
# Response schemas
# ═════════════════════════════════════════════════════════════════════════

class ImportResponse(BaseModel):
    """Result of a single import operation."""

    model_config = ConfigDict(from_attributes=True)

    source_id: uuid.UUID = Field(
        ...,
        description="ID of the created KnowledgeSource record.",
    )
    status: str = Field(
        ...,
        description='Processing status: "pending", "processing", "completed", "failed".',
    )
    chunks: int = Field(
        0,
        description="Number of text chunks generated.",
    )
    entities: int = Field(
        0,
        description="Number of entities extracted.",
    )


class ImportBatchResponse(BaseModel):
    """Result of a batch import operation."""

    sources: list[ImportResponse] = Field(
        default_factory=list,
        description="Individual import results.",
    )
    total: int = Field(0, description="Total items submitted.")
    successful: int = Field(0, description="Successfully processed items.")
    failed: int = Field(0, description="Failed items.")


# ═════════════════════════════════════════════════════════════════════════
# Pipeline importer response schemas
# ═════════════════════════════════════════════════════════════════════════

class IMessageImportResponse(BaseModel):
    """Result of an iMessage database import."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        ...,
        description='Processing status: "completed" or "failed".',
    )
    messages_imported: int = Field(
        0,
        description="Total number of messages imported.",
    )
    contacts_found: int = Field(
        0,
        description="Number of unique contacts discovered.",
    )
    entities_extracted: int = Field(
        0,
        description="Number of entities extracted from message content.",
    )
    error: Optional[str] = Field(
        None,
        description="Error detail if the import failed.",
    )


class GmailImportResponse(BaseModel):
    """Result of a Gmail import."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        ...,
        description='Processing status: "completed" or "failed".',
    )
    emails_imported: int = Field(
        0,
        description="Total number of emails imported.",
    )
    contacts_found: int = Field(
        0,
        description="Number of unique contacts discovered.",
    )
    entities_extracted: int = Field(
        0,
        description="Number of entities extracted from email content.",
    )
    error: Optional[str] = Field(
        None,
        description="Error detail if the import failed.",
    )


class FacebookImportResponse(BaseModel):
    """Result of a Facebook data export import."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        ...,
        description='Processing status: "completed" or "failed".',
    )
    messages_imported: int = Field(
        0,
        description="Total number of Facebook messages imported.",
    )
    friends_found: int = Field(
        0,
        description="Number of friends discovered from the export.",
    )
    posts_imported: int = Field(
        0,
        description="Number of user posts imported.",
    )
    entities_extracted: int = Field(
        0,
        description="Number of entities extracted from content.",
    )
    error: Optional[str] = Field(
        None,
        description="Error detail if the import failed.",
    )
