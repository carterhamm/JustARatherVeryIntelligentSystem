"""
Facebook data export importer for J.A.R.V.I.S.

Accepts the path to an extracted Facebook data export directory (or a ZIP
file that will be extracted automatically).  Imports conversations, friend
lists, and posts into the knowledge graph and vector store.

Supported Facebook export files
-------------------------------
- ``messages/inbox/*/message_1.json`` -- Conversations
- ``friends_and_followers/friends.json`` -- Friend list
- ``posts/your_posts_1.json`` -- User posts
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import structlog

from app.graphrag.entity_extractor import Entity, EntityExtractor, Relationship
from app.graphrag.graph_store import GraphStore
from app.graphrag.vector_store import VectorStore

logger = structlog.get_logger("jarvis.importers.facebook")

# Window size for grouping messages before embedding
_MESSAGE_WINDOW = 20


def _decode_fb_text(text: str) -> str:
    """Facebook exports encode non-ASCII characters as escaped UTF-8 byte
    sequences (e.g. ``\\u00c3\\u00a9`` for ``e``).  This function decodes
    them back to proper Unicode."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


class FacebookImporter:
    """Import data from a Facebook data export into the JARVIS knowledge base."""

    @staticmethod
    async def import_data(
        user_id: str,
        data_path: str,
        graph_store: GraphStore,
        vector_store: VectorStore,
        entity_extractor: EntityExtractor,
    ) -> dict[str, Any]:
        """Import Facebook export data.

        Parameters
        ----------
        user_id:
            The JARVIS user ID performing the import.
        data_path:
            Path to the extracted Facebook export directory **or** a
            ``.zip`` file containing the export.
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
            ``friends_found``, ``posts_imported``, and
            ``entities_extracted``.
        """
        log = logger.bind(user_id=user_id, data_path=data_path)
        log.info("facebook_import.started")

        export_dir: Path
        temp_dir: str | None = None

        path = Path(data_path)

        # If the path is a ZIP file, extract to a temporary directory
        if path.is_file() and path.suffix.lower() == ".zip":
            temp_dir = tempfile.mkdtemp(prefix="jarvis_fb_")
            log.info("facebook_import.extracting_zip", dest=temp_dir)
            try:
                with zipfile.ZipFile(str(path), "r") as zf:
                    zf.extractall(temp_dir)
            except zipfile.BadZipFile:
                log.error("facebook_import.bad_zip")
                raise ValueError(f"Invalid ZIP file: {data_path}")
            export_dir = Path(temp_dir)
            # Facebook exports sometimes have a single root directory
            subdirs = [d for d in export_dir.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                export_dir = subdirs[0]
        elif path.is_dir():
            export_dir = path
        else:
            raise FileNotFoundError(
                f"Facebook export not found at {data_path}. "
                "Provide a directory or a .zip file."
            )

        try:
            # ── Create user node ────────────────────────────────────────
            user_entity = Entity(
                name="User",
                type="PERSON",
                description="The JARVIS system owner",
            )
            await graph_store.add_entity(user_entity, user_id=user_id)

            messages_imported = 0
            friends_found = 0
            posts_imported = 0
            entities_extracted = 0

            # ── Import friends ──────────────────────────────────────────
            friends_result = await FacebookImporter._import_friends(
                export_dir, user_id, graph_store, log
            )
            friends_found = friends_result

            # ── Import conversations ────────────────────────────────────
            msgs_result = await FacebookImporter._import_messages(
                export_dir,
                user_id,
                graph_store,
                vector_store,
                entity_extractor,
                log,
            )
            messages_imported = msgs_result["messages_imported"]
            entities_extracted += msgs_result["entities_extracted"]

            # ── Import posts ────────────────────────────────────────────
            posts_result = await FacebookImporter._import_posts(
                export_dir,
                user_id,
                graph_store,
                vector_store,
                entity_extractor,
                log,
            )
            posts_imported = posts_result["posts_imported"]
            entities_extracted += posts_result["entities_extracted"]

            stats = {
                "messages_imported": messages_imported,
                "friends_found": friends_found,
                "posts_imported": posts_imported,
                "entities_extracted": entities_extracted,
            }
            log.info("facebook_import.completed", **stats)
            return stats

        finally:
            # Clean up temporary extraction directory
            if temp_dir is not None:
                try:
                    shutil.rmtree(temp_dir)
                    log.info("facebook_import.temp_cleaned", path=temp_dir)
                except Exception as exc:
                    log.warning(
                        "facebook_import.temp_cleanup_failed",
                        path=temp_dir,
                        error=str(exc),
                    )

    # ── Friends import ───────────────────────────────────────────────────

    @staticmethod
    async def _import_friends(
        export_dir: Path,
        user_id: str,
        graph_store: GraphStore,
        log: Any,
    ) -> int:
        """Parse the friends list and create Person nodes with KNOWS
        relationships."""
        friends_file = export_dir / "friends_and_followers" / "friends.json"
        if not friends_file.exists():
            log.info("facebook_import.no_friends_file")
            return 0

        try:
            data = json.loads(friends_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("facebook_import.friends_parse_error", error=str(exc))
            return 0

        # Facebook friends.json can have different structures depending on
        # the export version.  Handle both list-of-objects and
        # {"friends_v2": [...]} formats.
        friends_list: list[dict[str, Any]] = []
        if isinstance(data, list):
            friends_list = data
        elif isinstance(data, dict):
            # Try common keys
            for key in ("friends_v2", "friends", "data"):
                if key in data and isinstance(data[key], list):
                    friends_list = data[key]
                    break
            if not friends_list and isinstance(data, dict):
                # Fallback: treat entire dict values as potential lists
                for val in data.values():
                    if isinstance(val, list):
                        friends_list = val
                        break

        count = 0
        for friend in friends_list:
            name = friend.get("name", "")
            if not name:
                continue
            name = _decode_fb_text(name)

            friend_entity = Entity(
                name=name,
                type="PERSON",
                description="Facebook friend",
            )
            await graph_store.add_entity(friend_entity, user_id=user_id)

            relationship = Relationship(
                source="User",
                target=name,
                type="KNOWS",
                description="Facebook friendship",
                weight=1.0,
            )
            await graph_store.add_relationship(relationship, user_id=user_id)
            count += 1

        log.info("facebook_import.friends_imported", count=count)
        return count

    # ── Messages import ──────────────────────────────────────────────────

    @staticmethod
    async def _import_messages(
        export_dir: Path,
        user_id: str,
        graph_store: GraphStore,
        vector_store: VectorStore,
        entity_extractor: EntityExtractor,
        log: Any,
    ) -> dict[str, int]:
        """Parse Facebook Messenger conversations from the export."""
        inbox_dir = export_dir / "messages" / "inbox"
        if not inbox_dir.exists():
            log.info("facebook_import.no_messages_dir")
            return {"messages_imported": 0, "entities_extracted": 0}

        messages_imported = 0
        entities_extracted = 0

        # Each conversation is in its own subdirectory
        for convo_dir in sorted(inbox_dir.iterdir()):
            if not convo_dir.is_dir():
                continue

            msg_file = convo_dir / "message_1.json"
            if not msg_file.exists():
                continue

            try:
                data = json.loads(msg_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning(
                    "facebook_import.message_parse_error",
                    conversation=convo_dir.name,
                    error=str(exc),
                )
                continue

            participants = data.get("participants", [])
            messages = data.get("messages", [])

            if not messages:
                continue

            # Create Person nodes for participants
            for participant in participants:
                name = _decode_fb_text(participant.get("name", ""))
                if not name:
                    continue
                p_entity = Entity(
                    name=name,
                    type="PERSON",
                    description="Facebook Messenger contact",
                )
                await graph_store.add_entity(p_entity, user_id=user_id)

                relationship = Relationship(
                    source="User",
                    target=name,
                    type="COMMUNICATED_WITH",
                    description=f"Facebook Messenger conversation with {name}",
                    weight=1.0,
                )
                await graph_store.add_relationship(relationship, user_id=user_id)

            # Process messages in windows
            for i in range(0, len(messages), _MESSAGE_WINDOW):
                window = messages[i : i + _MESSAGE_WINDOW]
                lines: list[str] = []

                for msg in window:
                    sender = _decode_fb_text(msg.get("sender_name", "Unknown"))
                    content = _decode_fb_text(msg.get("content", ""))
                    timestamp_ms = msg.get("timestamp_ms", 0)

                    if not content:
                        continue

                    lines.append(f"[{timestamp_ms}] {sender}: {content}")
                    messages_imported += 1

                if not lines:
                    continue

                window_text = "\n".join(lines)

                # Store embedding
                chunk_id = hashlib.sha256(
                    f"facebook:msg:{user_id}:{convo_dir.name}:{i}".encode()
                ).hexdigest()[:32]

                try:
                    await vector_store.add_document(
                        doc_id=chunk_id,
                        text=window_text,
                        metadata={
                            "user_id": user_id,
                            "source_type": "facebook_message",
                            "conversation": convo_dir.name,
                            "window_index": i,
                        },
                    )
                except Exception as exc:
                    log.warning(
                        "facebook_import.message_embedding_failed",
                        conversation=convo_dir.name,
                        window_index=i,
                        error=str(exc),
                    )

                # Extract entities
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
                        "facebook_import.message_entity_extraction_failed",
                        conversation=convo_dir.name,
                        window_index=i,
                        error=str(exc),
                    )

        log.info(
            "facebook_import.messages_done",
            messages_imported=messages_imported,
            entities_extracted=entities_extracted,
        )
        return {
            "messages_imported": messages_imported,
            "entities_extracted": entities_extracted,
        }

    # ── Posts import ─────────────────────────────────────────────────────

    @staticmethod
    async def _import_posts(
        export_dir: Path,
        user_id: str,
        graph_store: GraphStore,
        vector_store: VectorStore,
        entity_extractor: EntityExtractor,
        log: Any,
    ) -> dict[str, int]:
        """Parse the user's Facebook posts from the export."""
        posts_file = export_dir / "posts" / "your_posts_1.json"
        if not posts_file.exists():
            log.info("facebook_import.no_posts_file")
            return {"posts_imported": 0, "entities_extracted": 0}

        try:
            data = json.loads(posts_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("facebook_import.posts_parse_error", error=str(exc))
            return {"posts_imported": 0, "entities_extracted": 0}

        # Posts can be a list directly or nested under a key
        posts_list: list[dict[str, Any]] = []
        if isinstance(data, list):
            posts_list = data
        elif isinstance(data, dict):
            for key in ("posts", "data"):
                if key in data and isinstance(data[key], list):
                    posts_list = data[key]
                    break

        posts_imported = 0
        entities_extracted = 0

        for idx, post in enumerate(posts_list):
            # Extract post text from the nested structure
            post_text = ""
            post_data = post.get("data", [])
            if isinstance(post_data, list):
                for item in post_data:
                    if isinstance(item, dict) and "post" in item:
                        post_text = _decode_fb_text(item["post"])
                        break

            # Some exports have the text directly
            if not post_text:
                post_text = _decode_fb_text(post.get("post", ""))
            if not post_text:
                post_text = _decode_fb_text(post.get("text", ""))
            if not post_text:
                post_text = _decode_fb_text(post.get("title", ""))

            if not post_text:
                continue

            timestamp = post.get("timestamp", 0)

            full_text = f"Facebook post ({timestamp}):\n{post_text}"

            # Store embedding
            chunk_id = hashlib.sha256(
                f"facebook:post:{user_id}:{idx}".encode()
            ).hexdigest()[:32]

            try:
                await vector_store.add_document(
                    doc_id=chunk_id,
                    text=full_text,
                    metadata={
                        "user_id": user_id,
                        "source_type": "facebook_post",
                        "timestamp": timestamp,
                        "post_index": idx,
                    },
                )
            except Exception as exc:
                log.warning(
                    "facebook_import.post_embedding_failed",
                    post_index=idx,
                    error=str(exc),
                )

            # Extract entities
            try:
                entities, relationships = await entity_extractor.extract_all(
                    full_text
                )
                for entity in entities:
                    await graph_store.add_entity(entity, user_id=user_id)
                for rel in relationships:
                    await graph_store.add_relationship(rel, user_id=user_id)
                entities_extracted += len(entities)
            except Exception as exc:
                log.warning(
                    "facebook_import.post_entity_extraction_failed",
                    post_index=idx,
                    error=str(exc),
                )

            posts_imported += 1

        log.info(
            "facebook_import.posts_done",
            posts_imported=posts_imported,
            entities_extracted=entities_extracted,
        )
        return {
            "posts_imported": posts_imported,
            "entities_extracted": entities_extracted,
        }
