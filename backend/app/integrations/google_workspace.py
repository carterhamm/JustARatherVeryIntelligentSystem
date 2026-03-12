"""
Google Workspace integration for JARVIS.

Provides Gmail, Calendar, Drive, and Sheets access using per-user
OAuth tokens stored in user preferences. Each user connects their
own Google account via the OAuth flow at /api/v1/google/auth-url.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _get_credentials(google_tokens: dict) -> Any:
    """Build Google credentials from stored token data."""
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=google_tokens.get("token"),
        refresh_token=google_tokens.get("refresh_token"),
        token_uri=google_tokens.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=google_tokens.get("client_id"),
        client_secret=google_tokens.get("client_secret"),
        scopes=google_tokens.get("scopes"),
    )


def _build_service(google_tokens: dict, service_name: str, version: str) -> Any:
    """Build a Google API service client from stored tokens."""
    from googleapiclient.discovery import build

    creds = _get_credentials(google_tokens)
    return build(service_name, version, credentials=creds)


# ── Gmail ────────────────────────────────────────────────────────────────

async def gmail_read(
    google_tokens: dict,
    query: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Read emails from Gmail."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "gmail", "v1")
        results = service.users().messages().list(
            userId="me",
            q=query or "is:inbox",
            maxResults=limit,
        ).execute()

        messages = results.get("messages", [])
        emails = []
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            snippet = msg.get("snippet", "")
            emails.append({
                "id": msg["id"],
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": snippet,
                "labels": msg.get("labelIds", []),
            })
        return emails

    return await asyncio.to_thread(_sync)


async def gmail_unread_count(
    google_tokens: dict,
) -> dict[str, Any]:
    """Return the number of unread inbox messages and a few recent subject lines."""
    import asyncio

    def _sync() -> dict[str, Any]:
        service = _build_service(google_tokens, "gmail", "v1")

        # Use labels.get for the fast unread count (single API call)
        label_info = service.users().labels().get(
            userId="me", id="INBOX",
        ).execute()
        unread = label_info.get("messagesUnread", 0)

        # Grab a handful of recent unread subject lines
        results = service.users().messages().list(
            userId="me",
            q="is:inbox is:unread",
            maxResults=5,
        ).execute()
        recent: list[dict[str, str]] = []
        for msg_ref in results.get("messages", []):
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            recent.append({
                "subject": headers.get("Subject", "(no subject)"),
                "from": headers.get("From", ""),
            })

        return {"unread_count": unread, "recent": recent}

    return await asyncio.to_thread(_sync)


async def gmail_important_recent(
    google_tokens: dict,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Fetch recent non-promotional inbox emails from the past 7 days.

    Returns a list of dicts with: subject, from, date, snippet, message_id.
    Excludes promotions, social, updates, and forums categories.
    """
    import asyncio

    def _sync() -> list[dict[str, Any]]:
        service = _build_service(google_tokens, "gmail", "v1")

        results = service.users().messages().list(
            userId="me",
            q="is:inbox newer_than:7d -category:promotions -category:social -category:updates -category:forums",
            maxResults=max_results,
        ).execute()

        emails: list[dict[str, Any]] = []
        for msg_ref in results.get("messages", []):
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            emails.append({
                "subject": headers.get("Subject", "(no subject)"),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "message_id": msg["id"],
            })

        return emails

    return await asyncio.to_thread(_sync)


async def gmail_send(
    google_tokens: dict,
    to: str,
    subject: str,
    body: str,
) -> dict[str, str]:
    """Send an email via Gmail."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "gmail", "v1")
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()
        return {"id": result["id"], "status": "sent"}

    return await asyncio.to_thread(_sync)


async def gmail_read_full(
    google_tokens: dict,
    message_id: str,
) -> dict[str, Any]:
    """Read a full email message by ID."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "gmail", "v1")
        msg = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Extract body text
        body = ""
        payload = msg.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break

        return {
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body,
            "labels": msg.get("labelIds", []),
        }

    return await asyncio.to_thread(_sync)


# ── Calendar ─────────────────────────────────────────────────────────────

async def calendar_list_events(
    google_tokens: dict,
    start_date: str,
    end_date: str,
    calendar_id: str = "primary",
) -> list[dict[str, Any]]:
    """List calendar events within a date range."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "calendar", "v3")

        # Ensure proper datetime format
        time_min = start_date if "T" in start_date else f"{start_date}T00:00:00Z"
        time_max = end_date if "T" in end_date else f"{end_date}T23:59:59Z"

        results = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()

        events = []
        for event in results.get("items", []):
            start = event.get("start", {})
            end = event.get("end", {})
            events.append({
                "id": event["id"],
                "title": event.get("summary", ""),
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
                "location": event.get("location", ""),
                "description": event.get("description", ""),
                "status": event.get("status", ""),
            })
        return events

    return await asyncio.to_thread(_sync)


async def calendar_create_event(
    google_tokens: dict,
    title: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a calendar event."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "calendar", "v3")

        event_body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "America/Denver"},
            "end": {"dateTime": end, "timeZone": "America/Denver"},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees]

        result = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
        ).execute()

        return {
            "id": result["id"],
            "title": result.get("summary", ""),
            "start": result["start"].get("dateTime", ""),
            "end": result["end"].get("dateTime", ""),
            "link": result.get("htmlLink", ""),
        }

    return await asyncio.to_thread(_sync)


# ── Drive ────────────────────────────────────────────────────────────────

async def drive_list_files(
    google_tokens: dict,
    query: str = "",
    folder_id: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """List or search files in Google Drive."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "drive", "v3")

        q_parts = []
        if query:
            q_parts.append(f"name contains '{query}'")
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        q_parts.append("trashed = false")
        q_string = " and ".join(q_parts)

        results = service.files().list(
            q=q_string,
            pageSize=limit,
            fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()

        return [
            {
                "id": f["id"],
                "name": f["name"],
                "type": f.get("mimeType", ""),
                "modified": f.get("modifiedTime", ""),
                "size": f.get("size", ""),
                "link": f.get("webViewLink", ""),
            }
            for f in results.get("files", [])
        ]

    return await asyncio.to_thread(_sync)


# ── Sheets ───────────────────────────────────────────────────────────────

async def sheets_read(
    google_tokens: dict,
    spreadsheet_id: str,
    range_name: str = "Sheet1",
) -> list[list[str]]:
    """Read data from a Google Sheets spreadsheet."""
    import asyncio
    def _sync():
        service = _build_service(google_tokens, "sheets", "v4")
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
        return result.get("values", [])

    return await asyncio.to_thread(_sync)
