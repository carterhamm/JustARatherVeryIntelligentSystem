"""J.A.R.V.I.S. FastAPI application entry-point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import v1_router
from app.config import settings
from app.core.events import shutdown_handler, startup_handler
from app.core.middleware import RequestLoggingMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
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
    # Disable Swagger/ReDoc in production to reduce attack surface
    docs_kwargs = {}
    if not settings.DEBUG:
        docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

    application = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Just A Rather Very Intelligent System",
        lifespan=lifespan,
        **docs_kwargs,
    )

    # -- CORS -----------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Device-Trust"],
        expose_headers=["X-Request-ID"],
    )

    # -- Custom middleware (outermost first) -----------------------------------
    application.add_middleware(SecurityHeadersMiddleware)
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

        # SPA fallback: serve index.html for 404s on non-API routes
        @application.exception_handler(StarletteHTTPException)
        async def spa_fallback(request: Request, exc: StarletteHTTPException) -> FileResponse | JSONResponse:
            # Only serve SPA for 404s on non-API GET requests
            if exc.status_code == 404 and not request.url.path.startswith("/api/") and request.method == "GET":
                # Serve static file if it exists
                rel_path = request.url.path.lstrip("/")
                if rel_path:
                    file_path = (STATIC_DIR / rel_path).resolve()
                    static_root = STATIC_DIR.resolve()
                    if file_path.is_file() and str(file_path).startswith(str(static_root)):
                        return FileResponse(str(file_path))
                return FileResponse(str(index_html))
            # All other HTTP exceptions: return JSON
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    else:
        logger.info("No frontend build found at %s — API-only mode", STATIC_DIR)

    return application


# Module-level app instance used by uvicorn
app = create_app()
