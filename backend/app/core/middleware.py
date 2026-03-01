"""Custom ASGI middleware for request logging and rate-limiting."""

import time
from collections import defaultdict
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.stdlib.get_logger("jarvis.middleware")


# ---------------------------------------------------------------------------
# Request logging
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            client=request.client.host if request.client else "unknown",
        )

        return response


# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (for development / single-process)
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter keyed by client IP.

    Parameters
    ----------
    max_requests:
        Maximum number of requests allowed inside *window_seconds*.
    window_seconds:
        Sliding-window duration in seconds.
    """

    def __init__(self, app: Callable, max_requests: int = 120, window_seconds: int = 60) -> None:  # type: ignore[override]
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _clean_bucket(self, bucket: list[float], now: float) -> list[float]:
        """Remove timestamps older than the current window."""
        cutoff = now - self.window_seconds
        return [ts for ts in bucket if ts > cutoff]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        self._buckets[client_ip] = self._clean_bucket(self._buckets[client_ip], now)

        if len(self._buckets[client_ip]) >= self.max_requests:
            logger.warning("rate_limit_exceeded", client=client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )

        self._buckets[client_ip].append(now)
        return await call_next(request)
