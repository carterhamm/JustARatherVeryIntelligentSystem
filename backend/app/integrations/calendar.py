"""
Async Google Calendar client for the J.A.R.V.I.S. system.

Provides calendar event management via the Google Calendar API v3 using
OAuth2 credentials.  All HTTP communication is performed through *httpx*
for seamless integration with asyncio-based servers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.calendar")

_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds

_DEFAULT_CALENDAR_ID = "primary"


class CalendarClient:
    """
    Async client for the Google Calendar REST API (v3).

    Uses Google OAuth2 access tokens, refreshing automatically when they
    expire.  All methods are async and use *httpx* under the hood.
    """

    def __init__(
        self,
        credentials: Optional[dict[str, str]] = None,
        calendar_id: str = _DEFAULT_CALENDAR_ID,
        timeout: float = 30.0,
    ) -> None:
        creds = credentials or {}
        self._client_id = creds.get("client_id", settings.GOOGLE_CLIENT_ID)
        self._client_secret = creds.get("client_secret", settings.GOOGLE_CLIENT_SECRET)
        self._refresh_token = creds.get("refresh_token", settings.GOOGLE_REFRESH_TOKEN)
        self._access_token: Optional[str] = creds.get("access_token")
        self._calendar_id = calendar_id

        self._http = httpx.AsyncClient(
            base_url=_CALENDAR_API_BASE,
            timeout=httpx.Timeout(timeout),
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def create_event(
        self,
        summary: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        description: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        location: Optional[str] = None,
        *,
        title: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a calendar event.

        Parameters
        ----------
        summary:
            Event title / summary.  The ``title`` kwarg is accepted as
            an alias for compatibility with the tool layer.
        start:
            ISO 8601 datetime string for the event start.
        end:
            ISO 8601 datetime string for the event end.
        description:
            Optional event description / notes.
        attendees:
            Optional list of attendee email addresses.
        location:
            Optional event location string.
        title:
            Alias for *summary* (used by the agent tool layer).

        Returns
        -------
        dict
            Calendar API event resource, augmented with convenience keys
            ``title``, ``start``, ``end``, and ``event_id``.
        """
        event_summary = summary or title or "Untitled Event"

        event_body: dict[str, Any] = {
            "summary": event_summary,
            "start": self._format_datetime(start or ""),
            "end": self._format_datetime(end or ""),
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": a} for a in attendees]

        data = await self._request(
            "POST",
            f"/calendars/{self._calendar_id}/events",
            json=event_body,
        )

        logger.info(
            "Calendar event created: id=%s summary=%r",
            data.get("id"),
            event_summary,
        )
        return {
            **data,
            "title": event_summary,
            "start": start,
            "end": end,
            "event_id": data.get("id", ""),
        }

    async def list_events(
        self,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 10,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        List calendar events within a time range.

        Parameters
        ----------
        time_min:
            Lower bound (inclusive) for event start time (ISO 8601).
            ``start_date`` is accepted as an alias.
        time_max:
            Upper bound (exclusive) for event start time (ISO 8601).
            ``end_date`` is accepted as an alias.
        max_results:
            Maximum number of events to return.

        Returns
        -------
        list[dict]
            Each dict contains ``event_id``, ``title``, ``start``,
            ``end``, ``description``, and ``location``.
        """
        effective_min = time_min or start_date
        effective_max = time_max or end_date

        params: dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if effective_min:
            params["timeMin"] = self._ensure_rfc3339(effective_min)
        if effective_max:
            params["timeMax"] = self._ensure_rfc3339(effective_max)

        data = await self._request(
            "GET",
            f"/calendars/{self._calendar_id}/events",
            params=params,
        )

        events: list[dict[str, Any]] = []
        for item in data.get("items", []):
            events.append(self._parse_event(item))

        return events

    async def get_event(self, event_id: str) -> dict[str, Any]:
        """
        Retrieve a single calendar event by ID.

        Returns
        -------
        dict
            Parsed event with ``event_id``, ``title``, ``start``,
            ``end``, ``description``, and ``location``.
        """
        data = await self._request(
            "GET",
            f"/calendars/{self._calendar_id}/events/{event_id}",
        )
        return self._parse_event(data)

    async def update_event(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        """
        Update an existing calendar event.

        Accepts any combination of ``summary``, ``start``, ``end``,
        ``description``, ``location``, and ``attendees``.

        Returns
        -------
        dict
            Updated event resource.
        """
        patch_body: dict[str, Any] = {}
        if "summary" in kwargs:
            patch_body["summary"] = kwargs["summary"]
        if "title" in kwargs:
            patch_body["summary"] = kwargs["title"]
        if "start" in kwargs:
            patch_body["start"] = self._format_datetime(kwargs["start"])
        if "end" in kwargs:
            patch_body["end"] = self._format_datetime(kwargs["end"])
        if "description" in kwargs:
            patch_body["description"] = kwargs["description"]
        if "location" in kwargs:
            patch_body["location"] = kwargs["location"]
        if "attendees" in kwargs:
            patch_body["attendees"] = [{"email": a} for a in kwargs["attendees"]]

        data = await self._request(
            "PATCH",
            f"/calendars/{self._calendar_id}/events/{event_id}",
            json=patch_body,
        )

        logger.info("Calendar event updated: id=%s", event_id)
        return self._parse_event(data)

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete a calendar event by ID.

        Returns
        -------
        bool
            ``True`` if the event was successfully deleted.
        """
        token = await self._ensure_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        response = await self._http.delete(
            f"/calendars/{self._calendar_id}/events/{event_id}",
            headers=headers,
        )

        if response.status_code == 401:
            self._access_token = None
            token = await self._ensure_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            response = await self._http.delete(
                f"/calendars/{self._calendar_id}/events/{event_id}",
                headers=headers,
            )

        response.raise_for_status()
        logger.info("Calendar event deleted: id=%s", event_id)
        return True

    # ── OAuth2 Token Management ──────────────────────────────────────────

    async def _ensure_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if self._access_token:
            return self._access_token

        if not self._refresh_token:
            raise RuntimeError(
                "No Calendar access token or refresh token available. "
                "Configure GOOGLE_REFRESH_TOKEN in settings."
            )

        self._access_token = await self._refresh_access_token()
        return self._access_token

    async def _refresh_access_token(self) -> str:
        """Exchange the refresh token for a new access token."""
        logger.info("Refreshing Google OAuth2 access token for Calendar")
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                _OAUTH_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            data = response.json()

        token = data.get("access_token", "")
        if not token:
            raise RuntimeError("OAuth2 token refresh returned empty access_token")

        logger.info("Google OAuth2 access token refreshed successfully (Calendar)")
        return token

    # ── HTTP Helpers ─────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute an authenticated Calendar API request with automatic
        token refresh and retries for transient failures.
        """
        import asyncio

        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                token = await self._ensure_access_token()
                headers = {"Authorization": f"Bearer {token}"}

                response = await self._http.request(
                    method,
                    path,
                    headers=headers,
                    json=json,
                    params=params,
                )

                # If token expired, refresh and retry
                if response.status_code == 401:
                    logger.warning("Calendar API returned 401 -- refreshing token")
                    self._access_token = None
                    token = await self._ensure_access_token()
                    headers = {"Authorization": f"Bearer {token}"}
                    response = await self._http.request(
                        method,
                        path,
                        headers=headers,
                        json=json,
                        params=params,
                    )

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Calendar request failed (attempt %d/%d): %s -- retrying in %.1fs",
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except httpx.TransportError as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Calendar transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Calendar request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # ── Datetime / Parsing Helpers ───────────────────────────────────────

    @staticmethod
    def _format_datetime(dt_str: str) -> dict[str, str]:
        """
        Convert an ISO 8601 datetime string into the Google Calendar API
        ``{"dateTime": ..., "timeZone": ...}`` format.

        If the input looks like a date-only string (``YYYY-MM-DD``), the
        ``date`` key is used instead.
        """
        if not dt_str:
            return {"dateTime": datetime.now(tz=timezone.utc).isoformat()}

        # Date-only (all-day event)
        if len(dt_str) == 10:
            return {"date": dt_str}

        # Full datetime -- ensure timezone info is present
        if "T" in dt_str and ("+" in dt_str or "Z" in dt_str):
            return {"dateTime": dt_str}

        # Assume UTC if no timezone specified
        if "T" in dt_str:
            return {"dateTime": f"{dt_str}Z" if not dt_str.endswith("Z") else dt_str}

        return {"dateTime": dt_str}

    @staticmethod
    def _ensure_rfc3339(dt_str: str) -> str:
        """
        Ensure a datetime string is in RFC 3339 format for the Calendar API
        query parameters.
        """
        if not dt_str:
            return datetime.now(tz=timezone.utc).isoformat()

        # Already has timezone info (Z, +HH:MM, or -HH:MM offset)
        if dt_str.endswith("Z"):
            return dt_str
        # Check for timezone offset like +05:00 or -06:00 at the end
        import re
        if re.search(r'[+-]\d{2}:\d{2}$', dt_str):
            return dt_str

        # Date-only: append start of day in UTC
        if len(dt_str) == 10:
            return f"{dt_str}T00:00:00Z"

        # Datetime without timezone: assume UTC
        if "T" in dt_str:
            return f"{dt_str}Z"

        return dt_str

    @staticmethod
    def _parse_event(item: dict[str, Any]) -> dict[str, Any]:
        """
        Extract useful fields from a Google Calendar event resource.
        """
        start_raw = item.get("start", {})
        end_raw = item.get("end", {})

        return {
            "event_id": item.get("id", ""),
            "title": item.get("summary", "Untitled"),
            "start": start_raw.get("dateTime", start_raw.get("date", "")),
            "end": end_raw.get("dateTime", end_raw.get("date", "")),
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "attendees": [
                a.get("email", "") for a in item.get("attendees", [])
            ],
            "status": item.get("status", ""),
            "html_link": item.get("htmlLink", ""),
        }

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "CalendarClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
