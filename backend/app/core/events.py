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

    # -- Security validation --------------------------------------------------
    _validate_security_config()

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

    # -- Stark Protocol (self-hosted LLM) ------------------------------------
    if settings.STARK_PROTOCOL_ENABLED:
        try:
            from app.integrations.llm.stark_client import StarkProtocolClient
            endpoint = settings.STARK_PROTOCOL_URL
            stark = StarkProtocolClient(
                endpoint_url=endpoint,
                api_key=settings.STARK_PROTOCOL_API_KEY,
            )
            healthy = await stark.health_check(retries=2, delay=3.0)
            if healthy:
                logger.info("stark_protocol_connected", url=endpoint)
            else:
                logger.warning("stark_protocol_unavailable",
                              url=endpoint,
                              hint="Stark Protocol tools will fall back to other providers")
        except Exception as exc:
            logger.warning("stark_protocol_check_failed", error=str(exc))

    logger.info("startup_complete", app=settings.APP_NAME)


def _validate_security_config() -> None:
    """Validate that critical security settings are properly configured."""
    insecure_jwt_defaults = {"change-me-to-a-random-64-char-hex-string", ""}
    insecure_aes_defaults = {"change-me-to-a-valid-fernet-key", ""}

    if settings.JWT_SECRET_KEY in insecure_jwt_defaults:
        logger.critical(
            "INSECURE_JWT_SECRET",
            hint="JWT_SECRET_KEY is using a default value. Set a strong random key in .env",
        )
        if not settings.DEBUG:
            raise SystemExit("FATAL: JWT_SECRET_KEY is not configured. Refusing to start in production.")

    if len(settings.JWT_SECRET_KEY) < 32:
        logger.warning(
            "WEAK_JWT_SECRET",
            length=len(settings.JWT_SECRET_KEY),
            hint="JWT_SECRET_KEY should be at least 32 characters (64 hex chars recommended)",
        )

    if settings.AES_KEY in insecure_aes_defaults:
        logger.critical(
            "INSECURE_AES_KEY",
            hint="AES_KEY is using a default value. Set a valid Fernet key in .env",
        )
        if not settings.DEBUG:
            raise SystemExit("FATAL: AES_KEY is not configured. Refusing to start in production.")

    if settings.DEBUG:
        logger.warning("DEBUG_MODE_ENABLED", hint="Debug mode exposes Swagger docs and detailed errors. Disable in production.")
    else:
        logger.info("security_config_ok")


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
