"""
Async Gmail client for the J.A.R.V.I.S. system.

Provides email sending and reading via the Gmail API v1 using OAuth2
credentials.  All HTTP communication is performed through *httpx* for
seamless integration with asyncio-based servers.
"""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.gmail")

_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


class GmailClient:
    """
    Async client for the Gmail REST API (v1).

    Uses Google OAuth2 access tokens, refreshing automatically when they
    expire.  All methods are async and use *httpx* under the hood.
    """

    def __init__(
        self,
        credentials: Optional[dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        creds = credentials or {}
        self._client_id = creds.get("client_id", settings.GOOGLE_CLIENT_ID)
        self._client_secret = creds.get("client_secret", settings.GOOGLE_CLIENT_SECRET)
        self._refresh_token = creds.get("refresh_token", settings.GOOGLE_REFRESH_TOKEN)
        self._access_token: Optional[str] = creds.get("access_token")

        self._http = httpx.AsyncClient(
            base_url=_GMAIL_API_BASE,
            timeout=httpx.Timeout(timeout),
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send an email via the authenticated Gmail account.

        Parameters
        ----------
        to:
            Recipient email address.
        subject:
            Email subject line.
        body:
            Plain-text email body.
        cc:
            Optional comma-separated CC recipients.
        bcc:
            Optional comma-separated BCC recipients.

        Returns
        -------
        dict
            Gmail API response containing ``id``, ``threadId``, and
            ``labelIds``, plus convenience keys ``to``, ``subject``,
            and ``message_id``.
        """
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body, "plain"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        data = await self._request(
            "POST",
            "/users/me/messages/send",
            json={"raw": raw},
        )

        logger.info("Email sent to=%s subject=%r message_id=%s", to, subject, data.get("id"))
        return {
            **data,
            "to": to,
            "subject": subject,
            "message_id": data.get("id", ""),
        }

    async def read_emails(
        self,
        query: str = "",
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search and read emails matching an optional Gmail search query.

        Parameters
        ----------
        query:
            Gmail search query (same syntax as the web UI search bar).
        max_results:
            Maximum number of messages to return.

        Returns
        -------
        list[dict]
            Each dict contains ``id``, ``from``, ``to``, ``subject``,
            ``date``, ``snippet``, and ``body``.
        """
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query

        data = await self._request("GET", "/users/me/messages", params=params)
        message_refs = data.get("messages", [])

        if not message_refs:
            return []

        emails: list[dict[str, Any]] = []
        for ref in message_refs[:max_results]:
            email = await self.get_email(ref["id"])
            emails.append(email)

        return emails

    # Alias used by the ReadEmailTool
    list_emails = read_emails

    async def get_email(self, message_id: str) -> dict[str, Any]:
        """
        Retrieve a single email by its message ID.

        Returns
        -------
        dict
            Parsed email with ``id``, ``from``, ``to``, ``subject``,
            ``date``, ``snippet``, and ``body`` keys.
        """
        data = await self._request(
            "GET",
            f"/users/me/messages/{message_id}",
            params={"format": "full"},
        )
        return self._parse_message(data)

    async def list_labels(self) -> list[dict[str, Any]]:
        """
        List all Gmail labels for the authenticated account.

        Returns
        -------
        list[dict]
            Each dict contains ``id``, ``name``, and ``type``.
        """
        data = await self._request("GET", "/users/me/labels")
        return data.get("labels", [])

    # ── OAuth2 Token Management ──────────────────────────────────────────

    async def _ensure_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if self._access_token:
            return self._access_token

        if not self._refresh_token:
            raise RuntimeError(
                "No Gmail access token or refresh token available. "
                "Configure GOOGLE_REFRESH_TOKEN in settings."
            )

        self._access_token = await self._refresh_access_token()
        return self._access_token

    async def _refresh_access_token(self) -> str:
        """Exchange the refresh token for a new access token."""
        logger.info("Refreshing Google OAuth2 access token")
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

        logger.info("Google OAuth2 access token refreshed successfully")
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
        Execute an authenticated Gmail API request with automatic token
        refresh and retries for transient failures.
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
                    logger.warning("Gmail API returned 401 -- refreshing token")
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
                        "Gmail request failed (attempt %d/%d): %s -- retrying in %.1fs",
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
                    "Gmail transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Gmail request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # ── Message Parsing ──────────────────────────────────────────────────

    @staticmethod
    def _parse_message(data: dict[str, Any]) -> dict[str, Any]:
        """
        Extract useful fields from a Gmail API message resource.
        """
        headers = {
            h["name"].lower(): h["value"]
            for h in data.get("payload", {}).get("headers", [])
        }

        # Extract body text
        body = ""
        payload = data.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(
                        part["body"]["data"]
                    ).decode("utf-8", errors="replace")
                    break

        return {
            "id": data.get("id", ""),
            "thread_id": data.get("threadId", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(no subject)"),
            "date": headers.get("date", ""),
            "snippet": data.get("snippet", ""),
            "body": body,
            "label_ids": data.get("labelIds", []),
        }

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "GmailClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
