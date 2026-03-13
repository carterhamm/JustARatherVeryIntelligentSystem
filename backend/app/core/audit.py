"""Security audit logging for JARVIS."""

import logging
from datetime import datetime, timezone

audit_logger = logging.getLogger("jarvis.audit")


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
