"""
Neo4j-backed graph store for the JARVIS knowledge graph.

Provides CRUD operations on entities and relationships, full-text search,
N-hop neighbourhood traversal, and index management — all expressed as
Cypher queries executed through :class:`app.db.neo4j.Neo4jClient`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.neo4j import Neo4jClient
from app.graphrag.entity_extractor import Entity, Relationship

logger = logging.getLogger(__name__)


class GraphStore:
    """Persistent graph store backed by Neo4j."""

    def __init__(self, neo4j_client: Neo4jClient) -> None:
        self._db = neo4j_client

    # ── Index management ────────────────────────────────────────────────

    async def init_indexes(self) -> None:
        """
        Create full-text and property indexes required by the graph store.

        Safe to call repeatedly — uses ``IF NOT EXISTS``.
        """
        # Composite property index on Entity(name, type)
        await self._db.execute_write(
            "CREATE INDEX entity_name_type IF NOT EXISTS "
            "FOR (e:Entity) ON (e.name, e.type)"
        )
        # Full-text index across name + description for free-text search
        await self._db.execute_write(
            "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS "
            "FOR (e:Entity) ON EACH [e.name, e.description]"
        )
        # Index on user-scoped entities
        await self._db.execute_write(
            "CREATE INDEX entity_user IF NOT EXISTS "
            "FOR (e:Entity) ON (e.user_id)"
        )
        logger.info("Neo4j indexes initialised.")

    # ── Entity CRUD ─────────────────────────────────────────────────────

    async def add_entity(self, entity: Entity, user_id: Optional[str] = None) -> str:
        """
        Upsert an entity node.

        Uses MERGE on ``(name, type)`` so duplicate inserts are idempotent.
        Returns the entity name as its identifier.
        """
        query = (
            "MERGE (e:Entity {name: $name, type: $type}) "
            "SET e.description = $description, "
            "    e.properties = $properties, "
            "    e.user_id = $user_id, "
            "    e.updated_at = datetime() "
            "ON CREATE SET e.created_at = datetime() "
            "RETURN e.name AS name"
        )
        params = {
            "name": entity.name,
            "type": entity.type,
            "description": entity.description,
            "properties": entity.properties or {},
            "user_id": user_id,
        }
        await self._db.execute_write(query, params)
        return entity.name

    async def add_relationship(
        self,
        relationship: Relationship,
        user_id: Optional[str] = None,
    ) -> str:
        """
        Upsert a directed relationship between two entity nodes.

        Both endpoint entities are MERGEd first so the relationship never
        fails due to a missing node.  Returns a string identifier.
        """
        query = (
            "MERGE (s:Entity {name: $source}) "
            "MERGE (t:Entity {name: $target}) "
            "MERGE (s)-[r:RELATES {type: $rel_type}]->(t) "
            "SET r.description = $description, "
            "    r.weight = $weight, "
            "    r.user_id = $user_id, "
            "    r.updated_at = datetime() "
            "ON CREATE SET r.created_at = datetime() "
            "RETURN $source + '->' + $target AS id"
        )
        params = {
            "source": relationship.source,
            "target": relationship.target,
            "rel_type": relationship.type,
            "description": relationship.description,
            "weight": relationship.weight,
            "user_id": user_id,
        }
        result = await self._db.execute_write(query, params)
        return f"{relationship.source}-[{relationship.type}]->{relationship.target}"

    async def get_entity(self, name: str) -> Optional[Entity]:
        """Look up a single entity by exact name.  Returns ``None`` if not found."""
        query = (
            "MATCH (e:Entity {name: $name}) "
            "RETURN e.name AS name, e.type AS type, "
            "       e.description AS description, e.properties AS properties "
            "LIMIT 1"
        )
        row = await self._db.execute_query_single(query, {"name": name})
        if row is None:
            return None
        return Entity(
            name=row["name"],
            type=row.get("type", "CONCEPT"),
            description=row.get("description", ""),
            properties=row.get("properties") or {},
        )

    async def search_entities(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Entity]:
        """
        Full-text search on entity names and descriptions.

        Falls back to a ``CONTAINS`` filter when the full-text index is
        not yet available (e.g. in test environments).
        """
        try:
            cypher = (
                "CALL db.index.fulltext.queryNodes('entity_fulltext', $query) "
                "YIELD node, score "
                "RETURN node.name AS name, node.type AS type, "
                "       node.description AS description, "
                "       node.properties AS properties, score "
                "ORDER BY score DESC "
                "LIMIT $limit"
            )
            rows = await self._db.execute_query(
                cypher, {"query": query, "limit": limit}
            )
        except Exception:
            # Fallback: substring match
            cypher = (
                "MATCH (e:Entity) "
                "WHERE toLower(e.name) CONTAINS toLower($query) "
                "   OR toLower(e.description) CONTAINS toLower($query) "
                "RETURN e.name AS name, e.type AS type, "
                "       e.description AS description, "
                "       e.properties AS properties "
                "LIMIT $limit"
            )
            rows = await self._db.execute_query(
                cypher, {"query": query, "limit": limit}
            )

        return [
            Entity(
                name=r["name"],
                type=r.get("type", "CONCEPT"),
                description=r.get("description", ""),
                properties=r.get("properties") or {},
            )
            for r in rows
        ]

    async def get_neighbors(
        self,
        entity_name: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        Traverse the graph up to *depth* hops from *entity_name* and return
        the discovered sub-graph as ``{"entities": [...], "relationships": [...]}``.
        """
        query = (
            "MATCH path = (start:Entity {name: $name})-[*1.." + str(int(depth)) + "]-(neighbor:Entity) "
            "UNWIND relationships(path) AS r "
            "WITH COLLECT(DISTINCT neighbor) AS neighbors, "
            "     COLLECT(DISTINCT r) AS rels, "
            "     start "
            "RETURN start, neighbors, rels"
        )
        rows = await self._db.execute_query(query, {"name": entity_name})

        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        seen_entities: set[str] = set()
        seen_rels: set[str] = set()

        for row in rows:
            # Start entity
            start_node = row.get("start")
            if start_node and isinstance(start_node, dict):
                sname = start_node.get("name", entity_name)
                if sname not in seen_entities:
                    seen_entities.add(sname)
                    entities.append({
                        "name": sname,
                        "type": start_node.get("type", "CONCEPT"),
                        "description": start_node.get("description", ""),
                        "properties": start_node.get("properties") or {},
                    })

            # Neighbor entities
            for n in row.get("neighbors", []):
                if isinstance(n, dict):
                    nname = n.get("name", "")
                    if nname and nname not in seen_entities:
                        seen_entities.add(nname)
                        entities.append({
                            "name": nname,
                            "type": n.get("type", "CONCEPT"),
                            "description": n.get("description", ""),
                            "properties": n.get("properties") or {},
                        })

            # Relationships
            for r in row.get("rels", []):
                if isinstance(r, dict):
                    key = f"{r.get('source', '')}->{r.get('target', '')}-{r.get('type', '')}"
                    if key not in seen_rels:
                        seen_rels.add(key)
                        relationships.append({
                            "source": r.get("source", ""),
                            "target": r.get("target", ""),
                            "type": r.get("type", "RELATED_TO"),
                            "description": r.get("description", ""),
                            "weight": r.get("weight", 1.0),
                        })

        # If the raw Neo4j records returned node objects instead of dicts,
        # fall back to a simpler two-step query.
        if not entities:
            entities, relationships = await self._get_neighbors_fallback(
                entity_name, depth
            )

        return {"entities": entities, "relationships": relationships}

    async def _get_neighbors_fallback(
        self,
        entity_name: str,
        depth: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Simpler two-query fallback for extracting a sub-graph when the
        single-query approach returns opaque node/relationship objects.
        """
        # Entities within N hops
        ent_query = (
            "MATCH (start:Entity {name: $name})-[*1.." + str(int(depth)) + "]-(n:Entity) "
            "WITH COLLECT(DISTINCT n) + COLLECT(DISTINCT start) AS all_nodes "
            "UNWIND all_nodes AS node "
            "RETURN DISTINCT node.name AS name, node.type AS type, "
            "       node.description AS description, "
            "       node.properties AS properties"
        )
        ent_rows = await self._db.execute_query(
            ent_query, {"name": entity_name}
        )
        entities = [
            {
                "name": r["name"],
                "type": r.get("type", "CONCEPT"),
                "description": r.get("description", ""),
                "properties": r.get("properties") or {},
            }
            for r in ent_rows
            if r.get("name")
        ]

        entity_names = {e["name"] for e in entities}

        # Relationships between those entities
        rel_query = (
            "MATCH (a:Entity)-[r:RELATES]->(b:Entity) "
            "WHERE a.name IN $names AND b.name IN $names "
            "RETURN a.name AS source, b.name AS target, "
            "       r.type AS type, r.description AS description, "
            "       r.weight AS weight"
        )
        rel_rows = await self._db.execute_query(
            rel_query, {"names": list(entity_names)}
        )
        relationships = [
            {
                "source": r["source"],
                "target": r["target"],
                "type": r.get("type", "RELATED_TO"),
                "description": r.get("description", ""),
                "weight": r.get("weight", 1.0),
            }
            for r in rel_rows
        ]

        return entities, relationships

    async def get_entity_context(self, entity_name: str) -> str:
        """
        Build a human-readable context string describing an entity and its
        immediate neighbourhood.  Suitable for injecting into an LLM prompt.
        """
        entity = await self.get_entity(entity_name)
        if entity is None:
            return f"No information found for entity '{entity_name}'."

        subgraph = await self.get_neighbors(entity_name, depth=2)

        lines: list[str] = [
            f"## Entity: {entity.name} ({entity.type})",
            f"Description: {entity.description}" if entity.description else "",
        ]

        if entity.properties:
            props = ", ".join(
                f"{k}: {v}" for k, v in entity.properties.items()
            )
            lines.append(f"Properties: {props}")

        neighbours = subgraph.get("entities", [])
        if neighbours:
            lines.append("\n### Related Entities")
            for n in neighbours:
                if n["name"] != entity_name:
                    lines.append(
                        f"- {n['name']} ({n['type']}): {n.get('description', '')}"
                    )

        rels = subgraph.get("relationships", [])
        if rels:
            lines.append("\n### Relationships")
            for r in rels:
                lines.append(
                    f"- {r['source']} --[{r['type']}]--> {r['target']}"
                    + (f": {r['description']}" if r.get("description") else "")
                )

        return "\n".join(line for line in lines if line)

    async def delete_entity(self, name: str) -> None:
        """
        Delete an entity and all its connected relationships.
        """
        query = (
            "MATCH (e:Entity {name: $name}) "
            "DETACH DELETE e"
        )
        await self._db.execute_write(query, {"name": name})
        logger.info("Deleted entity '%s' and its relationships.", name)

    async def delete_entities_by_source(self, source_id: str) -> None:
        """
        Remove all entities (and their relationships) associated with a
        given knowledge source ID.
        """
        query = (
            "MATCH (e:Entity {source_id: $source_id}) "
            "DETACH DELETE e"
        )
        await self._db.execute_write(query, {"source_id": source_id})
