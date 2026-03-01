"""
Async news client for the J.A.R.V.I.S. system.

Fetches top headlines and searches articles via the NewsAPI
(https://newsapi.org).  All HTTP communication is performed through
*httpx* for seamless integration with asyncio-based servers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.news")

# API base URL
_NEWSAPI_URL = "https://newsapi.org/v2"

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0  # seconds


class NewsClient:
    """
    Async news client backed by NewsAPI.

    Provides top-headline retrieval and full-text article search.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self._api_key = api_key or settings.NEWS_API_KEY
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
        )

    # -- Public API -----------------------------------------------------------

    async def get_headlines(
        self,
        country: str = "us",
        category: Optional[str] = None,
        page_size: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Fetch top headlines.

        Parameters
        ----------
        country:
            ISO 3166-1 alpha-2 country code (e.g. ``"us"``, ``"gb"``).
        category:
            Optional category filter -- ``"business"``, ``"entertainment"``,
            ``"general"``, ``"health"``, ``"science"``, ``"sports"``,
            ``"technology"``.
        page_size:
            Maximum number of articles to return (max 100).

        Returns
        -------
        list[dict]
            Each dict contains ``title``, ``description``, ``url``,
            ``source``, ``publishedAt``, ``urlToImage``, and ``author``.
        """
        if not self._api_key:
            logger.warning("No NEWS_API_KEY configured -- returning empty results")
            return []

        params: dict[str, Any] = {
            "apiKey": self._api_key,
            "country": country,
            "pageSize": min(page_size, 100),
        }
        if category:
            params["category"] = category

        data = await self._request("GET", f"{_NEWSAPI_URL}/top-headlines", params=params)
        return self._normalise_articles(data)

    async def search(
        self,
        query: str,
        sort_by: str = "relevancy",
        page_size: int = 10,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """
        Search for news articles matching a query.

        Parameters
        ----------
        query:
            Keywords or phrases to search for.
        sort_by:
            Sort order -- ``"relevancy"``, ``"popularity"``, or
            ``"publishedAt"``.
        page_size:
            Maximum number of articles to return (max 100).
        language:
            ISO 639-1 language code (e.g. ``"en"``).

        Returns
        -------
        list[dict]
            Same structure as :meth:`get_headlines`.
        """
        if not self._api_key:
            logger.warning("No NEWS_API_KEY configured -- returning empty results")
            return []

        if not query:
            return []

        params: dict[str, Any] = {
            "apiKey": self._api_key,
            "q": query,
            "sortBy": sort_by,
            "pageSize": min(page_size, 100),
            "language": language,
        }

        data = await self._request("GET", f"{_NEWSAPI_URL}/everything", params=params)
        return self._normalise_articles(data)

    # -- Normalisation helpers ------------------------------------------------

    @staticmethod
    def _normalise_articles(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten the raw NewsAPI response into a clean article list."""
        articles: list[dict[str, Any]] = []
        for item in data.get("articles", []):
            articles.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", ""),
                "source": item.get("source", {}).get("name", "Unknown"),
                "publishedAt": item.get("publishedAt", ""),
                "urlToImage": item.get("urlToImage", ""),
                "author": item.get("author", ""),
            })
        return articles

    # -- HTTP helpers ---------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retries for transient failures."""
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._http.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "News request failed (attempt %d/%d): %s -- retrying in %.1fs",
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
                    "News transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"News request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # -- Lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "NewsClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
