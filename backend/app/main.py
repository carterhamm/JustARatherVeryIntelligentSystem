"""J.A.R.V.I.S. FastAPI application entry-point."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import v1_router
from app.config import settings
from app.core.events import shutdown_handler, startup_handler
from app.core.middleware import RequestLoggingMiddleware, RateLimitMiddleware
from app.schemas.common import HealthResponse

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    await startup_handler(application)
    yield
    await shutdown_handler(application)


def create_app() -> FastAPI:
    """Application factory — builds and returns a fully configured FastAPI instance."""
    application = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Just A Rather Very Intelligent System",
        lifespan=lifespan,
    )

    # -- CORS -----------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Custom middleware (outermost first) -----------------------------------
    application.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)
    application.add_middleware(RequestLoggingMiddleware)

    # -- Routers --------------------------------------------------------------
    application.include_router(v1_router, prefix="/api/v1")

    # -- Health check ---------------------------------------------------------
    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check() -> HealthResponse:
        return HealthResponse(status="healthy", version="0.1.0")

    return application


# Module-level app instance used by uvicorn
app = create_app()
