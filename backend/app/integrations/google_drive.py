"""Google Drive API client — search, read, and create documents."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.google_drive")

_BASE_URL = "https://www.googleapis.com/drive/v3"
_DOCS_URL = "https://docs.googleapis.com/v1"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleDriveClient:
    """Async client for Google Drive and Docs APIs."""

    def __init__(self) -> None:
        self._access_token: str | None = None

    async def _get_access_token(self) -> str:
        """Exchange refresh token for a fresh access token."""
        if self._access_token:
            return self._access_token

        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REFRESH_TOKEN:
            raise ValueError("Google Drive is not configured (missing OAuth credentials).")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(_TOKEN_URL, data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": settings.GOOGLE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            })
            response.raise_for_status()
            data = response.json()

        self._access_token = data["access_token"]
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        token = await self._get_access_token()
        return {"Authorization": f"Bearer {token}"}

    async def search_files(
        self,
        query: str,
        max_results: int = 10,
        mime_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search Google Drive files."""
        headers = await self._headers()
        q_parts = [f"name contains '{query}' or fullText contains '{query}'"]
        if mime_type:
            q_parts.append(f"mimeType = '{mime_type}'")
        q_parts.append("trashed = false")
        q_string = " and ".join(q_parts)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_BASE_URL}/files",
                headers=headers,
                params={
                    "q": q_string,
                    "pageSize": max_results,
                    "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
                },
            )
            response.raise_for_status()

        return response.json().get("files", [])

    async def read_file(self, file_id: str) -> dict[str, Any]:
        """Read a file's metadata and content (text-based files only)."""
        headers = await self._headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get metadata
            meta_resp = await client.get(
                f"{_BASE_URL}/files/{file_id}",
                headers=headers,
                params={"fields": "id,name,mimeType,modifiedTime,size,webViewLink"},
            )
            meta_resp.raise_for_status()
            metadata = meta_resp.json()

            mime = metadata.get("mimeType", "")

            # For Google Docs, export as plain text
            if mime == "application/vnd.google-apps.document":
                content_resp = await client.get(
                    f"{_BASE_URL}/files/{file_id}/export",
                    headers=headers,
                    params={"mimeType": "text/plain"},
                )
                content_resp.raise_for_status()
                metadata["content"] = content_resp.text[:10000]
            elif mime.startswith("text/") or mime in (
                "application/json",
                "application/xml",
            ):
                content_resp = await client.get(
                    f"{_BASE_URL}/files/{file_id}",
                    headers=headers,
                    params={"alt": "media"},
                )
                content_resp.raise_for_status()
                metadata["content"] = content_resp.text[:10000]
            else:
                metadata["content"] = f"[Binary file: {mime}]"

        return metadata

    async def create_doc(self, title: str, content: str) -> dict[str, Any]:
        """Create a new Google Doc with the given title and content."""
        headers = await self._headers()
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create empty doc
            doc_resp = await client.post(
                f"{_DOCS_URL}/documents",
                headers=headers,
                json={"title": title},
            )
            doc_resp.raise_for_status()
            doc = doc_resp.json()
            doc_id = doc["documentId"]

            # Insert content
            if content:
                await client.post(
                    f"{_DOCS_URL}/documents/{doc_id}:batchUpdate",
                    headers=headers,
                    json={
                        "requests": [{
                            "insertText": {
                                "location": {"index": 1},
                                "text": content,
                            }
                        }]
                    },
                )

        return {
            "id": doc_id,
            "title": title,
            "url": f"https://docs.google.com/document/d/{doc_id}/edit",
        }
