"""J.A.R.V.I.S. FastAPI application entry-point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.v1 import v1_router
from app.config import settings
from app.core.events import shutdown_handler, startup_handler
from app.core.middleware import RequestLoggingMiddleware, RateLimitMiddleware
from app.schemas.common import HealthResponse

logger = structlog.stdlib.get_logger(__name__)

# Path to built frontend files (populated by Dockerfile)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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

    # -- Serve frontend static files (production) -----------------------------
    index_html = STATIC_DIR / "index.html"
    if STATIC_DIR.is_dir() and index_html.is_file():
        logger.info("Serving frontend from %s", STATIC_DIR)

        # Mount static assets (JS/CSS/images) at /assets
        assets_dir = STATIC_DIR / "assets"
        if assets_dir.is_dir():
            application.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # SPA fallback: any non-API route serves index.html
        @application.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            # Try to serve a static file first
            file_path = STATIC_DIR / full_path
            if full_path and file_path.is_file() and STATIC_DIR in file_path.resolve().parents:
                return FileResponse(str(file_path))
            return FileResponse(str(index_html))
    else:
        logger.info("No frontend build found at %s — API-only mode", STATIC_DIR)

    return application


# Module-level app instance used by uvicorn
app = create_app()
