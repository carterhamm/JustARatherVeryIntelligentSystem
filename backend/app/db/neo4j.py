"""
Neo4j async driver wrapper for the JARVIS knowledge graph.

Provides an async-compatible client that manages a single Neo4j driver
instance, executes Cypher queries (read and write), and supports use
as an async context manager.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession
from neo4j.exceptions import Neo4jError, ServiceUnavailable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton holder
# ---------------------------------------------------------------------------
_client: Optional["Neo4jClient"] = None


class Neo4jClient:
    """Async wrapper around the official Neo4j Python driver."""

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._max_pool = max_connection_pool_size
        self._driver: Optional[AsyncDriver] = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """Create the underlying Neo4j async driver and verify connectivity."""
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            max_connection_pool_size=self._max_pool,
        )
        try:
            await self._driver.verify_connectivity()
            logger.info("Neo4j connection established to %s", self._uri)
        except ServiceUnavailable:
            logger.error("Unable to reach Neo4j at %s", self._uri)
            raise

    async def close(self) -> None:
        """Gracefully shut down the driver."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed.")

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> "Neo4jClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # -- helpers -------------------------------------------------------------

    def _ensure_driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError(
                "Neo4jClient is not connected. Call connect() first."
            )
        return self._driver

    # -- query execution -----------------------------------------------------

    async def execute_query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a **read** transaction and return results as a list of dicts.

        Each dict maps the return columns to their values.
        """
        driver = self._ensure_driver()
        params = params or {}

        async with driver.session(database=self._database) as session:
            result = await session.run(query, params)
            records = await result.data()
            return records

    async def execute_write(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute a **write** transaction and return summary counters.

        Returns a dict with keys such as ``nodes_created``,
        ``relationships_created``, ``properties_set``, etc.
        """
        driver = self._ensure_driver()
        params = params or {}

        async with driver.session(database=self._database) as session:

            async def _work(tx: AsyncSession) -> dict[str, Any]:
                result = await tx.run(query, params)
                summary = await result.consume()
                counters = summary.counters
                return {
                    "nodes_created": counters.nodes_created,
                    "nodes_deleted": counters.nodes_deleted,
                    "relationships_created": counters.relationships_created,
                    "relationships_deleted": counters.relationships_deleted,
                    "properties_set": counters.properties_set,
                    "labels_added": counters.labels_added,
                    "labels_removed": counters.labels_removed,
                    "indexes_added": counters.indexes_added,
                    "indexes_removed": counters.indexes_removed,
                    "constraints_added": counters.constraints_added,
                    "constraints_removed": counters.constraints_removed,
                }

            return await session.execute_write(_work)

    async def execute_query_single(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Execute a read query and return the first record or ``None``."""
        results = await self.execute_query(query, params)
        return results[0] if results else None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_neo4j_client() -> Neo4jClient:
    """
    Return the module-level singleton Neo4jClient.

    The client is lazily constructed from ``app.config.settings`` on
    first call.  Callers must still ``await client.connect()`` (or use the
    client as an async context manager) before issuing queries.
    """
    global _client
    if _client is None:
        from app.config import settings

        _client = Neo4jClient(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
            database=getattr(settings, "NEO4J_DATABASE", "neo4j"),
        )
    return _client


async def close_neo4j_client() -> None:
    """Shut down the singleton client (call during app shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
