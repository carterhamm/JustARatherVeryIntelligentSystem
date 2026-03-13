"""Custom ASGI middleware for request logging, rate-limiting, and security headers."""

import json as _json
import re as _re
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
    """Token-bucket rate limiter keyed by client IP with path-based limits.

    Path-specific limits:
      - /api/v1/auth/*  -> 5 req/min  (login/register brute-force protection)
      - /api/v1/cron/*  -> 10 req/min (cron endpoints)
      - everything else -> 120 req/60s (default)

    Parameters
    ----------
    max_requests:
        Default maximum requests inside *window_seconds*.
    window_seconds:
        Sliding-window duration in seconds.
    """

    # Path prefix -> (max_requests, window_seconds)
    _PATH_LIMITS: dict[str, tuple[int, int]] = {
        "/api/v1/auth": (5, 60),
        "/api/v1/cron": (10, 60),
    }

    def __init__(self, app: Callable, max_requests: int = 120, window_seconds: int = 60) -> None:  # type: ignore[override]
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _get_limits(self, path: str) -> tuple[int, int]:
        """Return (max_requests, window_seconds) for the given request path."""
        for prefix, limits in self._PATH_LIMITS.items():
            if path.startswith(prefix):
                return limits
        return self.max_requests, self.window_seconds

    @staticmethod
    def _clean_bucket(bucket: list[float], now: float, window: int) -> list[float]:
        """Remove timestamps older than the current window."""
        cutoff = now - window
        return [ts for ts in bucket if ts > cutoff]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        now = time.time()

        max_req, window = self._get_limits(path)
        # Bucket key includes the path-limit tier so different limits don't share buckets
        bucket_key = f"{client_ip}:{max_req}:{window}"

        self._buckets[bucket_key] = self._clean_bucket(self._buckets[bucket_key], now, window)

        if len(self._buckets[bucket_key]) >= max_req:
            logger.warning(
                "rate_limit_exceeded",
                client=client_ip,
                path=path,
                limit=max_req,
                window=window,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )

        self._buckets[bucket_key].append(now)
        return await call_next(request)


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every HTTP response.

    Covers OWASP recommendations: HSTS, content-type sniffing, clickjacking,
    XSS reflection, referrer leakage, and permissions policy.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Strict Transport Security — force HTTPS for 1 year, include subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking — only allow same-origin framing
        response.headers["X-Frame-Options"] = "DENY"

        # XSS reflection filter (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy — don't leak full URL to third parties
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy — disable unnecessary browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"

        # Content Security Policy — restrict resource loading
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.apple-mapkit.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https://*.apple-mapkit.com https://*.apple.com https://*.ls.apple.com https://*.ssl.mzstatic.com; "
            "connect-src 'self' wss: ws: https://cdn.apple-mapkit.com https://*.apple-mapkit.com https://*.apple.com https://*.ls.apple.com; "
            "font-src 'self' data:; "
            "frame-ancestors 'none'"
        )

        return response


# ---------------------------------------------------------------------------
# Error sanitization — strip internal details from 5xx responses in production
# ---------------------------------------------------------------------------

# Patterns that suggest internal details are leaking
_LEAK_PATTERNS = _re.compile(
    r"(api[_-]?key|token|secret|password|https?://[^\s]+|Traceback)",
    _re.IGNORECASE,
)


class ErrorSanitizationMiddleware(BaseHTTPMiddleware):
    """Strip internal exception details from error responses in production.

    5xx responses that contain API keys, URLs, or tracebacks are replaced
    with a generic message.  The full error is still logged server-side.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        if response.status_code >= 500:
            from app.config import settings
            if not settings.DEBUG:
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk if isinstance(chunk, bytes) else chunk.encode()
                try:
                    body = _json.loads(body_bytes)
                    detail = body.get("detail", "")
                    if isinstance(detail, str) and _LEAK_PATTERNS.search(detail):
                        op = detail.split(" failed")[0] if " failed" in detail else "Operation"
                        body["detail"] = f"{op} failed. Please try again later."
                        return JSONResponse(content=body, status_code=response.status_code)
                except (ValueError, AttributeError):
                    pass
                return Response(content=body_bytes, status_code=response.status_code,
                                media_type=response.media_type)

        return response


# ---------------------------------------------------------------------------
# HTTPS enforcement
# ---------------------------------------------------------------------------


class HTTPSEnforcementMiddleware(BaseHTTPMiddleware):
    """Reject non-HTTPS requests in production.

    Checks X-Forwarded-Proto (set by Railway/Cloudflare load balancer)
    since the app itself runs behind a reverse proxy on HTTP.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.config import settings
        if not settings.DEBUG:
            proto = request.headers.get("x-forwarded-proto", "https")
            if proto != "https" and not request.url.path.startswith("/health"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "HTTPS required"},
                )
        return await call_next(request)
