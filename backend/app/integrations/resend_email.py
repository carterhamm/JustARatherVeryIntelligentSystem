"""Resend integration — outbound email from jarvis@malibupoint.dev.

HARD RULE: JARVIS only sends emails TO the owner (Carter).
Never send email impersonating the owner to third parties.
"""

from __future__ import annotations

import logging
from typing import Optional

import resend

from app.config import settings

logger = logging.getLogger("jarvis.resend")


def _init_resend() -> bool:
    """Initialize Resend with API key. Returns True if configured."""
    if not settings.RESEND_API_KEY:
        return False
    resend.api_key = settings.RESEND_API_KEY
    return True


async def send_email(
    to: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> dict:
    """Send an email from jarvis@malibupoint.dev.

    Parameters
    ----------
    to : str
        Recipient email address.
    subject : str
        Email subject line.
    body : str
        Plain text body.
    html : str, optional
        HTML body (optional).
    """
    if not _init_resend():
        return {"error": "Resend not configured (missing RESEND_API_KEY)"}

    try:
        params: dict = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        if html:
            params["html"] = html

        result = resend.Emails.send(params)
        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", "unknown")
        logger.info("Email sent via Resend: to=%s subject=%s id=%s", to, subject, email_id)
        return {
            "success": True,
            "email_id": email_id,
            "to": to,
            "subject": subject,
        }
    except Exception as exc:
        logger.exception("Failed to send email via Resend: %s", exc)
        return {"error": str(exc)}
