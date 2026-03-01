"""
iMessage importer for J.A.R.V.I.S.

Reads the macOS ``chat.db`` SQLite database, extracts messages grouped by
conversation/contact, creates Person nodes and COMMUNICATED_WITH
relationships in the knowledge graph, generates embeddings for message
content, and extracts entities via the LLM-based EntityExtractor.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

from app.graphrag.entity_extractor import Entity, EntityExtractor, Relationship
from app.graphrag.graph_store import GraphStore
from app.graphrag.vector_store import VectorStore

logger = structlog.get_logger("jarvis.importers.imessage")

# Apple's Core Data epoch: 2001-01-01 00:00:00 UTC
_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# Nanoseconds per second (Apple timestamps in chat.db are in nanoseconds)
_NS_PER_SEC = 1_000_000_000

_MESSAGES_QUERY = """\
SELECT
    message.ROWID,
    message.text,
    message.date,
    message.is_from_me,
    handle.id as contact,
    chat.chat_identifier
FROM message
LEFT JOIN handle ON message.handle_id = handle.ROWID
LEFT JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
LEFT JOIN chat ON chat_message_join.chat_id = chat.ROWID
WHERE message.text IS NOT NULL
ORDER BY message.date ASC
"""

# Window size for grouping messages before embedding
_MESSAGE_WINDOW = 20


class IMessageImporter:
    """Import iMessage conversations from a macOS chat.db file."""

    @staticmethod
    def _apple_timestamp_to_datetime(apple_ts: int | float | None) -> datetime:
        """Convert an Apple Core Data timestamp (nanoseconds since
        2001-01-01) to a timezone-aware UTC datetime."""
        if apple_ts is None or apple_ts == 0:
            return _APPLE_EPOCH
        # Some older databases store seconds instead of nanoseconds.
        # Heuristic: if the value is unreasonably large for seconds
        # (> year 2100 from epoch), treat it as nanoseconds.
        if apple_ts > 5_000_000_000:
            seconds = apple_ts / _NS_PER_SEC
        else:
            seconds = float(apple_ts)
        return _APPLE_EPOCH + timedelta(seconds=seconds)

    @staticmethod
    def _read_messages_sync(db_path: str) -> list[dict[str, Any]]:
        """Synchronous helper that opens the SQLite database and fetches
        all messages.  Designed to run inside a thread pool."""
        path = Path(db_path)
        if not path.exists():
            raise FileNotFoundError(f"chat.db not found at {db_path}")

        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(_MESSAGES_QUERY)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    async def import_from_db(
        user_id: str,
        db_path: str,
        graph_store: GraphStore,
        vector_store: VectorStore,
        entity_extractor: EntityExtractor,
    ) -> dict[str, Any]:
        """Import iMessage data from a macOS ``chat.db`` file.

        Parameters
        ----------
        user_id:
            The JARVIS user ID performing the import.
        db_path:
            Filesystem path to the ``chat.db`` SQLite database.
        graph_store:
            Neo4j-backed graph store for entity/relationship persistence.
        vector_store:
            Qdrant-backed vector store for embedding storage.
        entity_extractor:
            LLM-backed entity extractor.

        Returns
        -------
        dict
            Import statistics with keys ``messages_imported``,
            ``contacts_found``, and ``entities_extracted``.
        """
        log = logger.bind(user_id=user_id, db_path=db_path)
        log.info("imessage_import.started")

        # Run synchronous SQLite read in a thread pool
        loop = asyncio.get_running_loop()
        try:
            raw_messages = await loop.run_in_executor(
                None, IMessageImporter._read_messages_sync, db_path
            )
        except FileNotFoundError:
            log.error("imessage_import.db_not_found")
            raise
        except Exception as exc:
            log.error("imessage_import.db_read_failed", error=str(exc))
            raise

        log.info("imessage_import.messages_read", count=len(raw_messages))

        # ── Group messages by conversation/contact ──────────────────────
        conversations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        contacts: set[str] = set()

        for row in raw_messages:
            contact = row.get("contact") or row.get("chat_identifier") or "unknown"
            contacts.add(contact)
            conversations[contact].append(row)

        log.info(
            "imessage_import.grouped",
            conversations=len(conversations),
            contacts=len(contacts),
        )

        # ── Create Person nodes and COMMUNICATED_WITH relationships ─────
        user_entity = Entity(
            name="User",
            type="PERSON",
            description="The JARVIS system owner",
        )
        await graph_store.add_entity(user_entity, user_id=user_id)

        for contact in contacts:
            contact_entity = Entity(
                name=contact,
                type="PERSON",
                description=f"iMessage contact: {contact}",
            )
            await graph_store.add_entity(contact_entity, user_id=user_id)

            relationship = Relationship(
                source="User",
                target=contact,
                type="COMMUNICATED_WITH",
                description=f"iMessage conversation with {contact}",
                weight=1.0,
            )
            await graph_store.add_relationship(relationship, user_id=user_id)

        # ── Process messages: extract entities and store embeddings ──────
        messages_imported = 0
        entities_extracted = 0

        for contact, msgs in conversations.items():
            # Process in windows
            for i in range(0, len(msgs), _MESSAGE_WINDOW):
                window = msgs[i : i + _MESSAGE_WINDOW]

                # Build text block for this window
                lines: list[str] = []
                for msg in window:
                    ts = IMessageImporter._apple_timestamp_to_datetime(
                        msg.get("date")
                    )
                    sender = "Me" if msg.get("is_from_me") else contact
                    text = msg.get("text", "")
                    lines.append(f"[{ts.isoformat()}] {sender}: {text}")

                window_text = "\n".join(lines)
                messages_imported += len(window)

                # Store embedding in vector store
                chunk_id = hashlib.sha256(
                    f"imessage:{user_id}:{contact}:{i}".encode()
                ).hexdigest()[:32]

                try:
                    await vector_store.add_document(
                        doc_id=chunk_id,
                        text=window_text,
                        metadata={
                            "user_id": user_id,
                            "source_type": "imessage",
                            "contact": contact,
                            "window_index": i,
                            "message_count": len(window),
                        },
                    )
                except Exception as exc:
                    log.warning(
                        "imessage_import.embedding_failed",
                        contact=contact,
                        window_index=i,
                        error=str(exc),
                    )

                # Extract entities from the message window
                try:
                    entities, relationships = await entity_extractor.extract_all(
                        window_text
                    )
                    for entity in entities:
                        await graph_store.add_entity(entity, user_id=user_id)
                    for rel in relationships:
                        await graph_store.add_relationship(rel, user_id=user_id)
                    entities_extracted += len(entities)
                except Exception as exc:
                    log.warning(
                        "imessage_import.entity_extraction_failed",
                        contact=contact,
                        window_index=i,
                        error=str(exc),
                    )

        stats = {
            "messages_imported": messages_imported,
            "contacts_found": len(contacts),
            "entities_extracted": entities_extracted,
        }
        log.info("imessage_import.completed", **stats)
        return stats
