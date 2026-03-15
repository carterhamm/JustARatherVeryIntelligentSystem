"""Application lifecycle event handlers (startup / shutdown)."""

import structlog
from fastapi import FastAPI

from app.config import settings

logger = structlog.stdlib.get_logger("jarvis.events")


async def startup_handler(app: FastAPI) -> None:
    """Run once when the application starts.

    Every external service probe is wrapped in try/except so that the
    application boots successfully even when individual services are
    unreachable.  Failures are logged as warnings, not fatal errors.
    """
    logger.info("startup", app=settings.APP_NAME, debug=settings.DEBUG)

    # -- Security validation --------------------------------------------------
    _validate_security_config()

    # -- PostgreSQL -----------------------------------------------------------
    try:
        from app.db.postgres import engine
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        logger.info("postgres_connected", url=settings.DATABASE_URL.split("@")[-1])
    except Exception as exc:
        logger.error("postgres_connection_failed", error=str(exc),
                     hint="Database queries will fail until PostgreSQL is reachable")

    # -- Redis ----------------------------------------------------------------
    try:
        from app.db.redis import get_redis_client
        redis = await get_redis_client()
        pong = await redis.client.ping()
        if pong:
            logger.info("redis_connected", url=settings.REDIS_URL)
    except Exception as exc:
        logger.warning("redis_connection_failed", error=str(exc),
                       hint="Caching disabled — app will operate without Redis")

    # -- Neo4j ----------------------------------------------------------------
    try:
        from app.db.neo4j import get_neo4j_client
        neo4j_client = get_neo4j_client()
        await neo4j_client.connect()
        logger.info("neo4j_connected", uri=settings.NEO4J_URI)
    except Exception as exc:
        logger.warning("neo4j_connection_failed", error=str(exc),
                       hint="Knowledge graph unavailable — non-critical")

    # -- Qdrant ---------------------------------------------------------------
    try:
        from app.db.qdrant import get_qdrant_store
        qdrant_store = get_qdrant_store()
        await qdrant_store.initialize()
        logger.info("qdrant_connected", url=settings.QDRANT_URL)
    except Exception as exc:
        logger.warning("qdrant_connection_failed", error=str(exc),
                       hint="Vector search unavailable — keyword fallback will be used")

    # -- iMCP (macOS native services) ----------------------------------------
    try:
        from app.integrations.mcp_client import get_imcp_client
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

    # -- NTP time sync --------------------------------------------------------
    try:
        from app.utils.ntp_time import get_ntp_offset
        offset = get_ntp_offset()  # triggers initial sync
        logger.info("ntp_synced", server="time.apple.com", offset_seconds=round(offset, 4))
    except Exception as exc:
        logger.warning("ntp_sync_failed", error=str(exc))

    # -- Service health summary -----------------------------------------------
    try:
        from app.services.health import ServiceHealth
        health = await ServiceHealth.check_all()
        up = [name for name, info in health.items() if info.get("ok")]
        down = [name for name, info in health.items() if not info.get("ok")]
        logger.info(
            "service_health_summary",
            services_up=up,
            services_down=down,
            total_up=len(up),
            total_down=len(down),
        )
    except Exception as exc:
        logger.warning("service_health_check_failed", error=str(exc))

    # -- Background learning scheduler ----------------------------------------
    try:
        import asyncio

        async def _learning_scheduler():
            """Run a learning cycle every 30 minutes, forever."""
            await asyncio.sleep(120)  # wait 2 min after boot for services to stabilize
            logger.info("learning_scheduler_started", interval_minutes=30)
            while True:
                try:
                    from app.services.continuous_learning import run_learning_cycle
                    result = await run_learning_cycle()
                    status = result.get("status", "?")
                    ingested = result.get("total_ingested", 0)
                    logger.info(
                        "learning_cycle_complete",
                        status=status,
                        ingested=ingested,
                    )
                except Exception as exc:
                    logger.warning("learning_cycle_failed", error=str(exc))
                await asyncio.sleep(1800)  # 30 minutes

        asyncio.create_task(_learning_scheduler())
        logger.info("learning_scheduler_registered", interval_minutes=30)
    except Exception as exc:
        logger.warning("learning_scheduler_failed_to_register", error=str(exc))

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

    Each cleanup step is individually wrapped so that a failure in one
    service (e.g. Redis already gone) doesn't prevent the others from
    shutting down cleanly.
    """
    logger.info("shutdown_started", app=settings.APP_NAME)

    try:
        from app.db.postgres import engine
        await engine.dispose()
        logger.info("postgres_disconnected")
    except Exception as exc:
        logger.warning("postgres_shutdown_error", error=str(exc))

    try:
        from app.db.redis import close_redis
        await close_redis()
        logger.info("redis_disconnected")
    except Exception as exc:
        logger.warning("redis_shutdown_error", error=str(exc))

    try:
        from app.db.neo4j import close_neo4j_client
        await close_neo4j_client()
        logger.info("neo4j_disconnected")
    except Exception as exc:
        logger.warning("neo4j_shutdown_error", error=str(exc))

    try:
        from app.db.qdrant import close_qdrant_store
        await close_qdrant_store()
        logger.info("qdrant_disconnected")
    except Exception as exc:
        logger.warning("qdrant_shutdown_error", error=str(exc))

    try:
        from app.integrations.mcp_client import close_imcp_client
        await close_imcp_client()
        logger.info("imcp_disconnected")
    except Exception as exc:
        logger.warning("imcp_shutdown_error", error=str(exc))

    logger.info("shutdown_complete", app=settings.APP_NAME)
