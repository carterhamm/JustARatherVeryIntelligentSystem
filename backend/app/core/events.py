"""Application lifecycle event handlers (startup / shutdown)."""

import structlog
from fastapi import FastAPI

from app.config import settings
from app.db.neo4j import close_neo4j_client, get_neo4j_client
from app.db.postgres import engine
from app.db.qdrant import close_qdrant_store, get_qdrant_store
from app.db.redis import close_redis, get_redis_client
from app.integrations.mcp_client import close_imcp_client, get_imcp_client

logger = structlog.stdlib.get_logger("jarvis.events")


async def startup_handler(app: FastAPI) -> None:
    """Run once when the application starts.

    * Verify that PostgreSQL is reachable.
    * Verify that Redis is reachable.
    * Log a friendly banner.
    """
    logger.info("startup", app=settings.APP_NAME, debug=settings.DEBUG)

    # -- PostgreSQL -----------------------------------------------------------
    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        logger.info("postgres_connected", url=settings.DATABASE_URL.split("@")[-1])
    except Exception as exc:
        logger.error("postgres_connection_failed", error=str(exc))

    # -- Redis ----------------------------------------------------------------
    try:
        redis = await get_redis_client()
        pong = await redis.client.ping()
        if pong:
            logger.info("redis_connected", url=settings.REDIS_URL)
    except Exception as exc:
        logger.error("redis_connection_failed", error=str(exc))

    # -- Neo4j ----------------------------------------------------------------
    try:
        neo4j_client = get_neo4j_client()
        await neo4j_client.connect()
        logger.info("neo4j_connected", uri=settings.NEO4J_URI)
    except Exception as exc:
        logger.error("neo4j_connection_failed", error=str(exc))

    # -- Qdrant ---------------------------------------------------------------
    try:
        qdrant_store = get_qdrant_store()
        await qdrant_store.initialize()
        logger.info("qdrant_connected", url=settings.QDRANT_URL)
    except Exception as exc:
        logger.error("qdrant_connection_failed", error=str(exc))

    # -- iMCP (macOS native services) ----------------------------------------
    try:
        imcp = get_imcp_client()
        await imcp.start()
        tools = await imcp.list_tools()
        logger.info("imcp_connected", tools_count=len(tools))
    except Exception as exc:
        logger.warning("imcp_not_available", error=str(exc),
                       hint="iMCP tools will fail — install iMCP.app or ignore if not on macOS")

    logger.info("startup_complete", app=settings.APP_NAME)


async def shutdown_handler(app: FastAPI) -> None:
    """Run once when the application shuts down.

    * Dispose the SQLAlchemy async engine (closes the connection pool).
    * Close the Redis connection.
    """
    logger.info("shutdown_started", app=settings.APP_NAME)

    await engine.dispose()
    logger.info("postgres_disconnected")

    await close_redis()
    logger.info("redis_disconnected")

    await close_neo4j_client()
    logger.info("neo4j_disconnected")

    await close_qdrant_store()
    logger.info("qdrant_disconnected")

    await close_imcp_client()
    logger.info("imcp_disconnected")

    logger.info("shutdown_complete", app=settings.APP_NAME)
