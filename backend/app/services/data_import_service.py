"""
Data import service for J.A.R.V.I.S.

Handles ingestion of text, documents (PDF/TXT/MD), emails, messages,
and URLs into the knowledge base.  Each import:

1. Creates a ``KnowledgeSource`` record in PostgreSQL.
2. Chunks the text.
3. Generates embeddings via OpenAI.
4. Upserts chunks into Qdrant.
5. (Optional) Extracts entities for the Neo4j knowledge graph.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.qdrant import QdrantStore, get_qdrant_store
from app.models.knowledge import KnowledgeSource
from app.schemas.data_import import ImportResponse

logger = logging.getLogger("jarvis.services.data_import")

# ── Chunking parameters ─────────────────────────────────────────────────
_CHUNK_SIZE = 512  # target tokens per chunk (approximated by characters / 4)
_CHUNK_OVERLAP = 64
_CHARS_PER_TOKEN = 4  # rough heuristic


class DataImportService:
    """Orchestrates data ingestion into the JARVIS knowledge base."""

    def __init__(
        self,
        db: AsyncSession,
        knowledge_service: Any = None,
    ) -> None:
        self._db = db
        self._knowledge_service = knowledge_service

    # ══════════════════════════════════════════════════════════════════
    # Public import methods
    # ══════════════════════════════════════════════════════════════════

    async def import_text(
        self,
        user_id: str,
        text: str,
        title: Optional[str] = None,
        source_type: str = "text",
    ) -> ImportResponse:
        """Import a raw text string into the knowledge base."""
        source = await self._create_source(
            user_id=user_id,
            source_type=source_type,
            title=title or _auto_title(text),
            content=text,
        )

        try:
            chunks = self._chunk_text(text)
            embeddings = await self._embed_chunks(chunks)
            await self._upsert_vectors(
                source_id=str(source.id),
                user_id=user_id,
                title=source.title or "",
                chunks=chunks,
                embeddings=embeddings,
                source_type=source_type,
            )
            entity_count = await self._extract_entities(
                source_id=str(source.id),
                user_id=user_id,
                text=text,
            )
            await self._update_source_status(
                source.id,
                status="completed",
                chunk_count=len(chunks),
                entity_count=entity_count,
            )
            return ImportResponse(
                source_id=source.id,
                status="completed",
                chunks=len(chunks),
                entities=entity_count,
            )
        except Exception as exc:
            logger.exception("Import failed for source %s: %s", source.id, exc)
            await self._update_source_status(source.id, status="failed")
            return ImportResponse(
                source_id=source.id,
                status="failed",
                chunks=0,
                entities=0,
            )

    async def import_document(
        self,
        user_id: str,
        file_data: bytes,
        filename: str,
    ) -> ImportResponse:
        """Import a document file (PDF, TXT, MD) into the knowledge base."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext == "pdf":
            text = self._extract_pdf_text(file_data)
        elif ext in ("txt", "md", "markdown", "rst"):
            text = file_data.decode("utf-8", errors="replace")
        else:
            return ImportResponse(
                source_id=uuid.uuid4(),
                status="failed",
                chunks=0,
                entities=0,
            )

        if not text.strip():
            return ImportResponse(
                source_id=uuid.uuid4(),
                status="failed",
                chunks=0,
                entities=0,
            )

        return await self.import_text(
            user_id=user_id,
            text=text,
            title=filename,
            source_type="document",
        )

    async def import_emails(
        self,
        user_id: str,
        email_data: list[dict[str, Any]],
    ) -> list[ImportResponse]:
        """Batch-import emails into the knowledge base.

        Each email dict should have: ``from``, ``to``, ``subject``,
        ``body``, ``date``.
        """
        results: list[ImportResponse] = []
        for email in email_data:
            subject = email.get("subject", "(no subject)")
            body = email.get("body", "")
            sender = email.get("from", "Unknown")
            date = email.get("date", "")
            text = (
                f"Email from {sender}\n"
                f"Subject: {subject}\n"
                f"Date: {date}\n\n"
                f"{body}"
            )
            result = await self.import_text(
                user_id=user_id,
                text=text,
                title=f"Email: {subject}",
                source_type="email",
            )
            results.append(result)
        return results

    async def import_messages(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
    ) -> list[ImportResponse]:
        """Import chat messages (iMessage, SMS, etc.) into the knowledge
        base.

        Each message dict should have: ``sender``, ``content``,
        ``timestamp``.  Messages are grouped into conversation windows
        and imported as single chunks.
        """
        if not messages:
            return []

        # Group consecutive messages into windows of ~20 messages
        window_size = 20
        results: list[ImportResponse] = []

        for i in range(0, len(messages), window_size):
            window = messages[i : i + window_size]
            lines: list[str] = []
            for msg in window:
                sender = msg.get("sender", "Unknown")
                content = msg.get("content", "")
                ts = msg.get("timestamp", "")
                lines.append(f"[{ts}] {sender}: {content}")

            text = "\n".join(lines)
            first_ts = window[0].get("timestamp", "")
            result = await self.import_text(
                user_id=user_id,
                text=text,
                title=f"Messages ({first_ts})",
                source_type="message",
            )
            results.append(result)
        return results

    async def import_url(
        self,
        user_id: str,
        url: str,
    ) -> ImportResponse:
        """Fetch a URL, extract its text content, and import."""
        text = await self._fetch_url_text(url)
        if not text.strip():
            return ImportResponse(
                source_id=uuid.uuid4(),
                status="failed",
                chunks=0,
                entities=0,
            )
        return await self.import_text(
            user_id=user_id,
            text=text,
            title=url,
            source_type="url",
        )

    async def get_import_status(
        self,
        source_id: uuid.UUID,
    ) -> Optional[ImportResponse]:
        """Retrieve the current status of an import job."""
        stmt = select(KnowledgeSource).where(KnowledgeSource.id == source_id)
        result = await self._db.execute(stmt)
        source = result.scalar_one_or_none()
        if source is None:
            return None
        return ImportResponse(
            source_id=source.id,
            status=source.status,
            chunks=source.chunk_count,
            entities=source.entity_count,
        )

    # ══════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════

    async def _create_source(
        self,
        user_id: str,
        source_type: str,
        title: str,
        content: str,
    ) -> KnowledgeSource:
        """Create and persist a KnowledgeSource record."""
        source = KnowledgeSource(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            source_type=source_type,
            title=title,
            content=content,
            status="processing",
        )
        self._db.add(source)
        await self._db.commit()
        await self._db.refresh(source)
        return source

    async def _update_source_status(
        self,
        source_id: uuid.UUID,
        status: str,
        chunk_count: int = 0,
        entity_count: int = 0,
    ) -> None:
        """Update the processing status of a KnowledgeSource."""
        stmt = (
            update(KnowledgeSource)
            .where(KnowledgeSource.id == source_id)
            .values(
                status=status,
                chunk_count=chunk_count,
                entity_count=entity_count,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks.

        Uses a simple character-based sliding window that respects
        sentence boundaries where possible.
        """
        char_limit = _CHUNK_SIZE * _CHARS_PER_TOKEN
        overlap_chars = _CHUNK_OVERLAP * _CHARS_PER_TOKEN

        if len(text) <= char_limit:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + char_limit

            # Try to break at sentence boundary
            if end < len(text):
                # Look backwards for a sentence-ending punctuation
                window = text[max(end - 200, start) : end]
                for sep in (". ", ".\n", "? ", "!\n", "! ", "?\n", "\n\n"):
                    last_sep = window.rfind(sep)
                    if last_sep != -1:
                        end = max(end - 200, start) + last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap_chars
            if start <= (end - char_limit):
                start = end  # prevent infinite loop on edge cases

        return chunks

    async def _embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of text chunks."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # OpenAI supports batch embedding
        response = await client.embeddings.create(
            input=chunks,
            model="text-embedding-3-small",
        )
        return [item.embedding for item in response.data]

    async def _upsert_vectors(
        self,
        source_id: str,
        user_id: str,
        title: str,
        chunks: list[str],
        embeddings: list[list[float]],
        source_type: str,
    ) -> None:
        """Upsert chunk vectors into Qdrant."""
        store: QdrantStore = get_qdrant_store()
        points: list[dict[str, Any]] = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = hashlib.md5(
                f"{source_id}:{i}".encode()
            ).hexdigest()
            points.append({
                "id": point_id,
                "vector": embedding,
                "payload": {
                    "source_id": source_id,
                    "user_id": user_id,
                    "title": title,
                    "text": chunk,
                    "chunk_index": i,
                    "source_type": source_type,
                },
            })
        await store.upsert_batch(points)
        logger.info(
            "Upserted %d vectors for source %s.", len(points), source_id,
        )

    async def _extract_entities(
        self,
        source_id: str,
        user_id: str,
        text: str,
    ) -> int:
        """Extract entities from text and persist to Neo4j.

        Uses a lightweight LLM call to identify named entities, then
        creates nodes and relationships in the knowledge graph.

        Returns the number of entities extracted.
        """
        # Use the knowledge_service if available (it handles the full
        # GraphRAG pipeline).  Otherwise, perform a simple extraction.
        if self._knowledge_service and hasattr(
            self._knowledge_service, "extract_entities"
        ):
            try:
                entities = await self._knowledge_service.extract_entities(
                    source_id=source_id,
                    user_id=user_id,
                    text=text,
                )
                return len(entities) if entities else 0
            except Exception as exc:
                logger.warning("Knowledge service entity extraction failed: %s", exc)
                return 0

        # Fallback: simple NER via LLM
        try:
            from app.integrations.llm_client import LLMClient

            llm = LLMClient(api_key=settings.OPENAI_API_KEY)
            result = await llm.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract all named entities (people, organizations, "
                            "locations, dates, products) from the following text.  "
                            "Return a JSON array of objects with 'name', 'type', "
                            "and 'context' keys.  No markdown fences."
                        ),
                    },
                    {"role": "user", "content": text[:4000]},
                ],
                temperature=0.0,
                max_tokens=1024,
            )
            import json

            raw = result.get("content", "[]")
            # Try to parse
            try:
                entities = json.loads(raw)
                if isinstance(entities, list):
                    return len(entities)
            except json.JSONDecodeError:
                pass
            return 0
        except Exception as exc:
            logger.warning("LLM entity extraction failed: %s", exc)
            return 0

    @staticmethod
    def _extract_pdf_text(file_data: bytes) -> str:
        """Extract text from a PDF file's bytes."""
        try:
            import io
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(file_data))
            pages: list[str] = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
        except ImportError:
            logger.warning(
                "pypdf not installed; PDF import unavailable.  "
                "Install with: pip install pypdf"
            )
            return ""
        except Exception as exc:
            logger.exception("PDF text extraction failed: %s", exc)
            return ""

    @staticmethod
    async def _fetch_url_text(url: str) -> str:
        """Fetch a URL and extract readable text content."""
        try:
            import httpx

            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                if "text/html" in content_type:
                    return _strip_html(resp.text)
                elif "text/plain" in content_type or "application/json" in content_type:
                    return resp.text
                else:
                    # Try to decode as text anyway
                    return resp.text
        except ImportError:
            logger.warning(
                "httpx not installed; URL import unavailable.  "
                "Install with: pip install httpx"
            )
            return ""
        except Exception as exc:
            logger.exception("URL fetch failed for %s: %s", url, exc)
            return ""


# ── Utility functions ────────────────────────────────────────────────────

def _auto_title(text: str, max_length: int = 80) -> str:
    """Generate a title from the first line of text."""
    first_line = text.strip().split("\n", 1)[0].strip()
    if len(first_line) > max_length:
        return first_line[:max_length].rsplit(" ", 1)[0] + "..."
    return first_line or "Untitled"


def _strip_html(html: str) -> str:
    """Crudely strip HTML tags and decode entities to extract text.

    For production, use ``beautifulsoup4`` or ``readability-lxml``.
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
    except ImportError:
        # Fallback: regex-based stripping
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()
