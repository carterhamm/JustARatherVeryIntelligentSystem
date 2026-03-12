"""iCloud Mail IMAP integration.

Apple provides no email API. We use IMAP with App-Specific Passwords
to fetch mail from iCloud. The user must generate an app-specific
password at appleid.apple.com > Sign-In & Security > App-Specific Passwords.

IMAP server: imap.mail.me.com:993 (SSL)
"""

from __future__ import annotations

import asyncio
import email
import email.header
import email.utils
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("jarvis.icloud_mail")

ICLOUD_IMAP_HOST = "imap.mail.me.com"
ICLOUD_IMAP_PORT = 993


def _decode_header(raw: str | None) -> str:
    """Decode RFC 2047 encoded email header."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_sender(from_header: str) -> str:
    """Extract a readable sender from the From header."""
    name, addr = email.utils.parseaddr(from_header)
    if name:
        return f"{_decode_header(name)} <{addr}>"
    return addr or from_header


async def icloud_fetch_recent(
    apple_id: str,
    app_password: str,
    max_results: int = 15,
    days: int = 7,
    folder: str = "INBOX",
) -> list[dict[str, Any]]:
    """Fetch recent emails from iCloud Mail via IMAP.

    Args:
        apple_id: The user's Apple ID email (e.g. user@icloud.com)
        app_password: App-Specific Password from appleid.apple.com
        max_results: Maximum number of emails to return
        days: How many days back to search
        folder: IMAP folder to search (default INBOX)

    Returns:
        List of dicts with: subject, from, date, snippet, message_id, source
    """

    def _sync() -> list[dict[str, Any]]:
        mail = imaplib.IMAP4_SSL(ICLOUD_IMAP_HOST, ICLOUD_IMAP_PORT)
        try:
            mail.login(apple_id, app_password)
            mail.select(folder, readonly=True)

            # Search for recent emails
            since_date = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).strftime("%d-%b-%Y")
            _, msg_ids = mail.search(None, f'(SINCE "{since_date}")')

            if not msg_ids[0]:
                return []

            # Get the most recent N message IDs
            id_list = msg_ids[0].split()
            recent_ids = id_list[-max_results:]  # Last N = most recent
            recent_ids.reverse()  # Most recent first

            emails: list[dict[str, Any]] = []
            for msg_id in recent_ids:
                try:
                    # Fetch headers + first part for snippet
                    _, data = mail.fetch(
                        msg_id,
                        "(RFC822.HEADER BODY.PEEK[TEXT]<0.500>)",
                    )
                    if not data or not data[0]:
                        continue

                    # Parse headers
                    header_data = None
                    body_snippet = ""
                    for part in data:
                        if isinstance(part, tuple):
                            desc = (
                                part[0].decode()
                                if isinstance(part[0], bytes)
                                else part[0]
                            )
                            if "HEADER" in desc.upper():
                                header_data = part[1]
                            elif (
                                "TEXT" in desc.upper() or "BODY" in desc.upper()
                            ):
                                raw_body = part[1]
                                if isinstance(raw_body, bytes):
                                    body_snippet = raw_body.decode(
                                        "utf-8", errors="replace"
                                    )[:300]

                    if header_data is None:
                        continue

                    msg = email.message_from_bytes(header_data)
                    subject = _decode_header(msg.get("Subject"))
                    from_raw = _decode_header(msg.get("From"))
                    date_raw = msg.get("Date", "")
                    message_id_raw = msg.get("Message-ID", msg_id.decode())

                    # Clean up snippet (remove HTML tags, excess whitespace)
                    snippet = re.sub(r"<[^>]+>", "", body_snippet)
                    snippet = re.sub(r"\s+", " ", snippet).strip()[:200]

                    emails.append(
                        {
                            "subject": subject or "(no subject)",
                            "from": _extract_sender(from_raw),
                            "date": date_raw,
                            "snippet": snippet,
                            "message_id": str(message_id_raw),
                            "source": "icloud",
                        }
                    )
                except Exception as exc:
                    logger.debug(
                        "Failed to parse iCloud email %s: %s", msg_id, exc
                    )
                    continue

            return emails
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    return await asyncio.to_thread(_sync)


async def icloud_unread_count(
    apple_id: str,
    app_password: str,
    folder: str = "INBOX",
) -> int:
    """Get the count of unread emails in iCloud inbox."""

    def _sync() -> int:
        mail = imaplib.IMAP4_SSL(ICLOUD_IMAP_HOST, ICLOUD_IMAP_PORT)
        try:
            mail.login(apple_id, app_password)
            mail.select(folder, readonly=True)
            _, data = mail.search(None, "UNSEEN")
            if data[0]:
                return len(data[0].split())
            return 0
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    return await asyncio.to_thread(_sync)


async def icloud_search(
    apple_id: str,
    app_password: str,
    query: str = "",
    max_results: int = 10,
    folder: str = "INBOX",
) -> list[dict[str, Any]]:
    """Search iCloud mail by subject, sender, or flags.

    Args:
        apple_id: Apple ID email
        app_password: App-Specific Password
        query: Search string — maps to IMAP OR(FROM/SUBJECT) search.
               Special prefixes: "from:" searches sender, "subject:" searches
               subject, "unread" returns unseen messages, otherwise searches
               both FROM and SUBJECT.
        max_results: Maximum results
        folder: IMAP folder

    Returns:
        List of email dicts
    """

    def _sync() -> list[dict[str, Any]]:
        mail = imaplib.IMAP4_SSL(ICLOUD_IMAP_HOST, ICLOUD_IMAP_PORT)
        try:
            mail.login(apple_id, app_password)
            mail.select(folder, readonly=True)

            # Build IMAP search criteria
            q = query.strip()
            if not q or q.lower() == "all":
                criteria = "ALL"
            elif q.lower() in ("unread", "unseen", "is:unread"):
                criteria = "UNSEEN"
            elif q.lower().startswith("from:"):
                sender = q[5:].strip()
                criteria = f'(FROM "{sender}")'
            elif q.lower().startswith("subject:"):
                subj = q[8:].strip()
                criteria = f'(SUBJECT "{subj}")'
            else:
                # Search both FROM and SUBJECT
                criteria = f'(OR (FROM "{q}") (SUBJECT "{q}"))'

            _, msg_ids = mail.search(None, criteria)
            if not msg_ids[0]:
                return []

            id_list = msg_ids[0].split()
            recent_ids = id_list[-max_results:]
            recent_ids.reverse()

            emails: list[dict[str, Any]] = []
            for msg_id in recent_ids:
                try:
                    _, data = mail.fetch(
                        msg_id,
                        "(RFC822.HEADER BODY.PEEK[TEXT]<0.500>)",
                    )
                    if not data or not data[0]:
                        continue

                    header_data = None
                    body_snippet = ""
                    for part in data:
                        if isinstance(part, tuple):
                            desc = (
                                part[0].decode()
                                if isinstance(part[0], bytes)
                                else part[0]
                            )
                            if "HEADER" in desc.upper():
                                header_data = part[1]
                            elif (
                                "TEXT" in desc.upper() or "BODY" in desc.upper()
                            ):
                                raw_body = part[1]
                                if isinstance(raw_body, bytes):
                                    body_snippet = raw_body.decode(
                                        "utf-8", errors="replace"
                                    )[:300]

                    if header_data is None:
                        continue

                    msg = email.message_from_bytes(header_data)
                    subject = _decode_header(msg.get("Subject"))
                    from_raw = _decode_header(msg.get("From"))
                    date_raw = msg.get("Date", "")
                    message_id_raw = msg.get("Message-ID", msg_id.decode())

                    snippet = re.sub(r"<[^>]+>", "", body_snippet)
                    snippet = re.sub(r"\s+", " ", snippet).strip()[:200]

                    emails.append(
                        {
                            "subject": subject or "(no subject)",
                            "from": _extract_sender(from_raw),
                            "date": date_raw,
                            "snippet": snippet,
                            "message_id": str(message_id_raw),
                            "source": "icloud",
                        }
                    )
                except Exception as exc:
                    logger.debug(
                        "Failed to parse iCloud email %s: %s", msg_id, exc
                    )
                    continue

            return emails
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    return await asyncio.to_thread(_sync)
