"""
Data import API router for J.A.R.V.I.S.

Provides REST endpoints for ingesting text, files, URLs, and batches
of content into the knowledge base, as well as specialised importers
for iMessage, Gmail, and Facebook data.

Endpoints
---------
POST /import/text               Import raw text.
POST /import/file               Upload and import a file (PDF/TXT/MD).
POST /import/url                Import content from a URL.
POST /import/batch              Batch-import multiple items.
POST /import/imessage           Import iMessage chat.db database.
POST /import/gmail              Import emails from Gmail via OAuth.
POST /import/facebook           Import Facebook data export.
GET  /import/status/{source_id} Check import status.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openai import AsyncOpenAI

from app.config import settings
from app.core.dependencies import get_current_active_user
from app.db.neo4j import Neo4jClient
from app.db.qdrant import get_qdrant_store
from app.db.session import get_session
from app.graphrag.entity_extractor import EntityExtractor
from app.graphrag.graph_store import GraphStore
from app.graphrag.vector_store import VectorStore
from app.integrations.gmail import GmailClient
from app.models.user import User
from app.schemas.data_import import (
    FacebookImportResponse,
    GmailImportResponse,
    IMessageImportResponse,
    ImportBatchRequest,
    ImportBatchResponse,
    ImportResponse,
    ImportTextRequest,
    ImportURLRequest,
)
from app.services.data_import_service import DataImportService
from app.services.importers import FacebookImporter, GmailImporter, IMessageImporter

logger = structlog.get_logger("jarvis.api.data_import")

router = APIRouter(prefix="/import", tags=["Data Import"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def _get_import_service() -> DataImportService:
    """Provide the DataImportService with a real database session."""
    async for session in get_session():
        return DataImportService(db=session)
    # Fallback: should not reach here under normal operation
    raise RuntimeError("Could not obtain database session.")


# ═══════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════

@router.post(
    "/text",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import raw text into the knowledge base",
)
async def import_text(
    request: ImportTextRequest,
    current_user: User = Depends(get_current_active_user),
    svc: DataImportService = Depends(_get_import_service),
) -> ImportResponse:
    """Ingest a plain text snippet or note."""
    user_id = str(current_user.id)
    try:
        return await svc.import_text(
            user_id=user_id,
            text=request.content,
            title=request.title,
            source_type=request.source_type or "text",
        )
    except Exception as exc:
        logger.exception("Text import failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {exc}",
        )


@router.post(
    "/file",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and import a document (PDF, TXT, MD)",
)
async def import_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    svc: DataImportService = Depends(_get_import_service),
) -> ImportResponse:
    """Upload a document file for ingestion into the knowledge base."""
    user_id = str(current_user.id)
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    # Read file into memory (limit 50 MB)
    max_size = 50 * 1024 * 1024
    file_data = await file.read()
    if len(file_data) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 50 MB limit.",
        )

    try:
        return await svc.import_document(
            user_id=user_id,
            file_data=file_data,
            filename=file.filename,
        )
    except Exception as exc:
        logger.exception("File import failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File import failed: {exc}",
        )


@router.post(
    "/url",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import content from a URL",
)
async def import_url(
    request: ImportURLRequest,
    current_user: User = Depends(get_current_active_user),
    svc: DataImportService = Depends(_get_import_service),
) -> ImportResponse:
    """Fetch a URL, extract text, and ingest into the knowledge base."""
    user_id = str(current_user.id)
    try:
        return await svc.import_url(user_id=user_id, url=request.url)
    except Exception as exc:
        logger.exception("URL import failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"URL import failed: {exc}",
        )


@router.post(
    "/batch",
    response_model=ImportBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Batch-import multiple items",
)
async def import_batch(
    request: ImportBatchRequest,
    current_user: User = Depends(get_current_active_user),
    svc: DataImportService = Depends(_get_import_service),
) -> ImportBatchResponse:
    """Import multiple text snippets, URLs, emails, or messages in a
    single request."""
    user_id = str(current_user.id)
    results: list[ImportResponse] = []
    successful = 0
    failed = 0

    for item in request.items:
        try:
            if item.type == "text" and item.content:
                result = await svc.import_text(
                    user_id=user_id,
                    text=item.content,
                    title=item.title,
                    source_type="text",
                )
            elif item.type == "url" and item.url:
                result = await svc.import_url(
                    user_id=user_id,
                    url=item.url,
                )
            elif item.type == "email" and item.content:
                email_results = await svc.import_emails(
                    user_id=user_id,
                    email_data=[{
                        "subject": item.title or "(no subject)",
                        "body": item.content,
                        "from": (item.metadata or {}).get("from", "Unknown"),
                        "date": (item.metadata or {}).get("date", ""),
                    }],
                )
                result = email_results[0] if email_results else ImportResponse(
                    source_id=uuid.uuid4(), status="failed", chunks=0, entities=0,
                )
            elif item.type == "message" and item.content:
                msg_results = await svc.import_messages(
                    user_id=user_id,
                    messages=[{
                        "sender": (item.metadata or {}).get("sender", "Unknown"),
                        "content": item.content,
                        "timestamp": (item.metadata or {}).get("timestamp", ""),
                    }],
                )
                result = msg_results[0] if msg_results else ImportResponse(
                    source_id=uuid.uuid4(), status="failed", chunks=0, entities=0,
                )
            else:
                result = ImportResponse(
                    source_id=uuid.uuid4(),
                    status="failed",
                    chunks=0,
                    entities=0,
                )

            results.append(result)
            if result.status == "completed":
                successful += 1
            else:
                failed += 1
        except Exception as exc:
            logger.exception("Batch item import failed: %s", exc)
            results.append(ImportResponse(
                source_id=uuid.uuid4(),
                status="failed",
                chunks=0,
                entities=0,
            ))
            failed += 1

    return ImportBatchResponse(
        sources=results,
        total=len(request.items),
        successful=successful,
        failed=failed,
    )


@router.get(
    "/status/{source_id}",
    response_model=ImportResponse,
    summary="Check import status",
)
async def get_import_status(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    svc: DataImportService = Depends(_get_import_service),
) -> ImportResponse:
    """Retrieve the current status of a previously submitted import."""
    result = await svc.get_import_status(source_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import source {source_id} not found.",
        )
    return result


# ═══════════════════════════════════════════════════════════════════════
# Pipeline importer endpoints
# ═══════════════════════════════════════════════════════════════════════


def _get_graph_store() -> GraphStore:
    """Build a GraphStore backed by Neo4j."""
    neo4j_client = Neo4jClient(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
    )
    return GraphStore(neo4j_client)


def _get_vector_store() -> VectorStore:
    """Build a VectorStore backed by Qdrant with OpenAI embeddings."""
    qdrant = get_qdrant_store()
    oai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return VectorStore(qdrant_store=qdrant, embedding_client=oai)


def _get_entity_extractor() -> EntityExtractor:
    """Build an EntityExtractor backed by OpenAI."""
    oai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return EntityExtractor(llm_client=oai)


@router.post(
    "/imessage",
    response_model=IMessageImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import iMessage conversations from a chat.db file",
)
async def import_imessage(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> IMessageImportResponse:
    """Upload a macOS ``chat.db`` SQLite database and import all iMessage
    conversations into the knowledge graph and vector store."""
    user_id = str(current_user.id)
    log = logger.bind(user_id=user_id)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    # Save uploaded file to a temporary location
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix="jarvis_imessage_")
    try:
        file_data = await file.read()

        # Limit: 500 MB for chat.db
        max_size = 500 * 1024 * 1024
        if len(file_data) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 500 MB limit.",
            )

        os.write(tmp_fd, file_data)
        os.close(tmp_fd)

        graph_store = _get_graph_store()
        vector_store = _get_vector_store()
        entity_extractor = _get_entity_extractor()

        stats = await IMessageImporter.import_from_db(
            user_id=user_id,
            db_path=tmp_path,
            graph_store=graph_store,
            vector_store=vector_store,
            entity_extractor=entity_extractor,
        )

        return IMessageImportResponse(
            status="completed",
            messages_imported=stats["messages_imported"],
            contacts_found=stats["contacts_found"],
            entities_extracted=stats["entities_extracted"],
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        log.error("imessage_import.file_not_found", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid database file: {exc}",
        )
    except Exception as exc:
        log.exception("imessage_import.failed", error=str(exc))
        return IMessageImportResponse(
            status="failed",
            error=str(exc),
        )
    finally:
        # Clean up temporary file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post(
    "/gmail",
    response_model=GmailImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import emails from Gmail",
)
async def import_gmail(
    current_user: User = Depends(get_current_active_user),
) -> GmailImportResponse:
    """Trigger a Gmail import using stored OAuth credentials.  Fetches
    emails in batches and imports contacts, entities, and embeddings."""
    user_id = str(current_user.id)
    log = logger.bind(user_id=user_id)

    # Verify that Google OAuth credentials are configured
    if not settings.GOOGLE_REFRESH_TOKEN and not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Gmail OAuth credentials are not configured. "
                "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and "
                "GOOGLE_REFRESH_TOKEN in the environment."
            ),
        )

    try:
        async with GmailClient() as gmail_client:
            graph_store = _get_graph_store()
            vector_store = _get_vector_store()
            entity_extractor = _get_entity_extractor()

            stats = await GmailImporter.import_emails(
                user_id=user_id,
                gmail_client=gmail_client,
                graph_store=graph_store,
                vector_store=vector_store,
                entity_extractor=entity_extractor,
            )

        return GmailImportResponse(
            status="completed",
            emails_imported=stats["emails_imported"],
            contacts_found=stats["contacts_found"],
            entities_extracted=stats["entities_extracted"],
        )
    except Exception as exc:
        log.exception("gmail_import.failed", error=str(exc))
        return GmailImportResponse(
            status="failed",
            error=str(exc),
        )


@router.post(
    "/facebook",
    response_model=FacebookImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import Facebook data export",
)
async def import_facebook(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> FacebookImportResponse:
    """Upload a Facebook data export (ZIP file) and import conversations,
    friends, and posts into the knowledge graph and vector store."""
    user_id = str(current_user.id)
    log = logger.bind(user_id=user_id)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    # Save uploaded file to a temporary location
    suffix = ".zip" if file.filename.lower().endswith(".zip") else ""
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=suffix, prefix="jarvis_facebook_"
    )
    try:
        file_data = await file.read()

        # Limit: 2 GB for Facebook exports
        max_size = 2 * 1024 * 1024 * 1024
        if len(file_data) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 2 GB limit.",
            )

        os.write(tmp_fd, file_data)
        os.close(tmp_fd)

        graph_store = _get_graph_store()
        vector_store = _get_vector_store()
        entity_extractor = _get_entity_extractor()

        stats = await FacebookImporter.import_data(
            user_id=user_id,
            data_path=tmp_path,
            graph_store=graph_store,
            vector_store=vector_store,
            entity_extractor=entity_extractor,
        )

        return FacebookImportResponse(
            status="completed",
            messages_imported=stats["messages_imported"],
            friends_found=stats["friends_found"],
            posts_imported=stats["posts_imported"],
            entities_extracted=stats["entities_extracted"],
        )
    except HTTPException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        log.error("facebook_import.invalid_input", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        log.exception("facebook_import.failed", error=str(exc))
        return FacebookImportResponse(
            status="failed",
            error=str(exc),
        )
    finally:
        # Clean up temporary file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
