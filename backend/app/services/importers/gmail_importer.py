"""
Gmail importer for J.A.R.V.I.S.

Uses the GmailClient integration to fetch emails in batches, extract
contacts for the knowledge graph, create Person nodes and
COMMUNICATED_WITH relationships, extract entities from email content,
and store embeddings in the vector store.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import structlog

from app.graphrag.entity_extractor import Entity, EntityExtractor, Relationship
from app.graphrag.graph_store import GraphStore
from app.graphrag.vector_store import VectorStore
from app.integrations.gmail import GmailClient

logger = structlog.get_logger("jarvis.importers.gmail")

# Gmail API returns max 100 results per page
_GMAIL_BATCH_SIZE = 100

# Regex to extract email address from "Name <email>" format
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _extract_email_address(raw: str) -> str:
    """Pull a bare email address from a header value like
    ``"Tony Stark <tony@stark.com>"``."""
    match = _EMAIL_RE.search(raw)
    return match.group(0) if match else raw.strip()


def _extract_display_name(raw: str) -> str:
    """Extract the display name from an email header value.
    Falls back to the email address if no display name is present."""
    raw = raw.strip()
    if "<" in raw:
        name = raw.split("<")[0].strip().strip('"').strip("'")
        if name:
            return name
    return _extract_email_address(raw)


class GmailImporter:
    """Import emails from Gmail into the JARVIS knowledge base."""

    @staticmethod
    async def import_emails(
        user_id: str,
        gmail_client: GmailClient,
        graph_store: GraphStore,
        vector_store: VectorStore,
        entity_extractor: EntityExtractor,
        max_emails: int = 500,
    ) -> dict[str, Any]:
        """Fetch and import emails from Gmail.

        Parameters
        ----------
        user_id:
            The JARVIS user ID performing the import.
        gmail_client:
            An authenticated GmailClient instance.
        graph_store:
            Neo4j-backed graph store for entity/relationship persistence.
        vector_store:
            Qdrant-backed vector store for embedding storage.
        entity_extractor:
            LLM-backed entity extractor.
        max_emails:
            Maximum number of emails to import (default 500).

        Returns
        -------
        dict
            Import statistics with keys ``emails_imported``,
            ``contacts_found``, and ``entities_extracted``.
        """
        log = logger.bind(user_id=user_id, max_emails=max_emails)
        log.info("gmail_import.started")

        # ── Create the user node ────────────────────────────────────────
        user_entity = Entity(
            name="User",
            type="PERSON",
            description="The JARVIS system owner",
        )
        await graph_store.add_entity(user_entity, user_id=user_id)

        emails_imported = 0
        entities_extracted = 0
        contacts: set[str] = set()

        # ── Fetch emails in batches via pagination ──────────────────────
        remaining = max_emails
        while remaining > 0:
            batch_size = min(remaining, _GMAIL_BATCH_SIZE)
            try:
                emails = await gmail_client.read_emails(
                    query="",
                    max_results=batch_size,
                )
            except Exception as exc:
                log.error("gmail_import.fetch_failed", error=str(exc))
                break

            if not emails:
                log.info("gmail_import.no_more_emails")
                break

            for email in emails:
                email_id = email.get("id", "")
                sender = email.get("from", "")
                to = email.get("to", "")
                subject = email.get("subject", "(no subject)")
                body = email.get("body", "")
                snippet = email.get("snippet", "")
                date = email.get("date", "")

                # ── Extract and register contacts ───────────────────────
                email_contacts: list[str] = []
                for raw_contact in [sender, to]:
                    if not raw_contact:
                        continue
                    # Handle comma-separated recipients
                    for part in raw_contact.split(","):
                        part = part.strip()
                        if not part:
                            continue
                        addr = _extract_email_address(part)
                        display_name = _extract_display_name(part)
                        if addr and addr not in contacts:
                            contacts.add(addr)
                            contact_entity = Entity(
                                name=display_name,
                                type="PERSON",
                                description=f"Email contact: {addr}",
                                properties={"email": addr},
                            )
                            await graph_store.add_entity(
                                contact_entity, user_id=user_id
                            )
                            relationship = Relationship(
                                source="User",
                                target=display_name,
                                type="COMMUNICATED_WITH",
                                description=f"Email communication with {addr}",
                                weight=1.0,
                            )
                            await graph_store.add_relationship(
                                relationship, user_id=user_id
                            )
                        email_contacts.append(display_name)

                # ── Build text for embedding and entity extraction ──────
                email_text = (
                    f"Email from {sender}\n"
                    f"To: {to}\n"
                    f"Subject: {subject}\n"
                    f"Date: {date}\n\n"
                    f"{body or snippet}"
                )

                # ── Store embedding ─────────────────────────────────────
                chunk_id = hashlib.sha256(
                    f"gmail:{user_id}:{email_id}".encode()
                ).hexdigest()[:32]

                try:
                    await vector_store.add_document(
                        doc_id=chunk_id,
                        text=email_text,
                        metadata={
                            "user_id": user_id,
                            "source_type": "gmail",
                            "email_id": email_id,
                            "subject": subject,
                            "from": sender,
                            "to": to,
                            "date": date,
                        },
                    )
                except Exception as exc:
                    log.warning(
                        "gmail_import.embedding_failed",
                        email_id=email_id,
                        error=str(exc),
                    )

                # ── Extract entities ────────────────────────────────────
                try:
                    entities, relationships = await entity_extractor.extract_all(
                        email_text
                    )
                    for entity in entities:
                        await graph_store.add_entity(entity, user_id=user_id)
                    for rel in relationships:
                        await graph_store.add_relationship(rel, user_id=user_id)
                    entities_extracted += len(entities)
                except Exception as exc:
                    log.warning(
                        "gmail_import.entity_extraction_failed",
                        email_id=email_id,
                        error=str(exc),
                    )

                emails_imported += 1

            remaining -= len(emails)

            # If we got fewer than requested, there are no more pages
            if len(emails) < batch_size:
                break

        stats = {
            "emails_imported": emails_imported,
            "contacts_found": len(contacts),
            "entities_extracted": entities_extracted,
        }
        log.info("gmail_import.completed", **stats)
        return stats
