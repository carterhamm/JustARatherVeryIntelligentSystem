"""Security audit logging and error sanitization for JARVIS."""

import logging
from datetime import datetime, timezone

from app.config import settings

audit_logger = logging.getLogger("jarvis.audit")
_error_logger = logging.getLogger("jarvis.errors")


def log_audit(
    action: str,
    result: str,
    user_id: str = "",
    ip: str = "",
    details: str = "",
) -> None:
    """Emit a structured audit log entry for security-relevant events."""
    audit_logger.info(
        "AUDIT action=%s result=%s user=%s ip=%s details=%s ts=%s",
        action,
        result,
        user_id,
        ip,
        details,
        datetime.now(timezone.utc).isoformat(),
    )


def safe_error(operation: str, exc: Exception) -> str:
    """Return a sanitized error message for HTTP responses.

    In DEBUG mode, includes the exception. In production, logs the full
    error server-side but returns a generic message to the client.
    """
    _error_logger.error("%s failed: %s", operation, exc, exc_info=True)
    if settings.DEBUG:
        return f"{operation} failed: {exc}"
    return f"{operation} failed. Please try again later."
