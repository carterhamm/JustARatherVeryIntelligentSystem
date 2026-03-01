"""
Async web search client for the J.A.R.V.I.S. system.

Supports multiple search backends with automatic fallback:
  1. Tavily API  (primary)
  2. SerpAPI     (first fallback)
  3. Brave Search (second fallback)

All HTTP communication is performed through *httpx* for seamless
integration with asyncio-based servers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.web_search")

# API base URLs
_TAVILY_API_URL = "https://api.tavily.com"
_SERPAPI_API_URL = "https://serpapi.com"
_BRAVE_API_URL = "https://api.search.brave.com/res/v1"

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0  # seconds


class WebSearchClient:
    """
    Async web search client with multi-backend support.

    Tries Tavily first (richest content extraction), then falls back to
    SerpAPI and Brave Search if the primary is unavailable or unconfigured.
    """

    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        serpapi_api_key: Optional[str] = None,
        brave_api_key: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self._tavily_key = tavily_api_key or settings.TAVILY_API_KEY
        self._serpapi_key = serpapi_api_key or settings.SERPAPI_API_KEY
        self._brave_key = brave_api_key or settings.BRAVE_SEARCH_API_KEY

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search the web and return structured results.

        Tries each configured backend in priority order until one
        succeeds.

        Parameters
        ----------
        query:
            The search query string.
        max_results:
            Maximum number of results to return.

        Returns
        -------
        list[dict]
            Each dict contains ``title``, ``url``, ``snippet``, and
            ``content`` keys.
        """
        backends = []
        if self._tavily_key:
            backends.append(("tavily", self._search_tavily))
        if self._serpapi_key:
            backends.append(("serpapi", self._search_serpapi))
        if self._brave_key:
            backends.append(("brave", self._search_brave))

        if not backends:
            logger.warning("No search API keys configured -- returning empty results")
            return [{
                "title": "Search unavailable",
                "url": "",
                "snippet": (
                    "No search API keys are configured. Set TAVILY_API_KEY, "
                    "SERPAPI_API_KEY, or BRAVE_SEARCH_API_KEY in settings."
                ),
                "content": "",
            }]

        last_exc: BaseException | None = None
        for name, search_fn in backends:
            try:
                results = await search_fn(query, max_results)
                logger.info(
                    "Web search via %s returned %d result(s) for: %r",
                    name,
                    len(results),
                    query,
                )
                return results
            except Exception as exc:
                logger.warning(
                    "Search backend %s failed for query %r: %s -- trying next",
                    name,
                    query,
                    exc,
                )
                last_exc = exc

        logger.error("All search backends failed for query: %r", query)
        raise RuntimeError(
            f"All search backends failed for query: {query!r}"
        ) from last_exc

    # ── Tavily ───────────────────────────────────────────────────────────

    async def _search_tavily(
        self,
        query: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Execute a search via the Tavily API."""
        payload = {
            "api_key": self._tavily_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "search_depth": "basic",
        }

        data = await self._request(
            "POST",
            f"{_TAVILY_API_URL}/search",
            json=payload,
        )

        results: list[dict[str, Any]] = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:500],
                "content": item.get("raw_content", item.get("content", "")),
                "score": item.get("score", 0.0),
            })

        return results

    # ── SerpAPI ──────────────────────────────────────────────────────────

    async def _search_serpapi(
        self,
        query: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Execute a search via SerpAPI."""
        params = {
            "api_key": self._serpapi_key,
            "q": query,
            "num": max_results,
            "engine": "google",
        }

        data = await self._request(
            "GET",
            f"{_SERPAPI_API_URL}/search.json",
            params=params,
        )

        results: list[dict[str, Any]] = []
        for item in data.get("organic_results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "content": item.get("snippet", ""),
                "position": item.get("position", 0),
            })

        return results[:max_results]

    # ── Brave Search ─────────────────────────────────────────────────────

    async def _search_brave(
        self,
        query: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Execute a search via the Brave Search API."""
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._brave_key,
        }
        params = {
            "q": query,
            "count": max_results,
        }

        data = await self._request(
            "GET",
            f"{_BRAVE_API_URL}/web/search",
            params=params,
            headers=headers,
        )

        results: list[dict[str, Any]] = []
        web_results = data.get("web", {}).get("results", [])
        for item in web_results:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "content": item.get("description", ""),
            })

        return results[:max_results]

    # ── HTTP Helpers ─────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """
        Execute an HTTP request with retries for transient failures.
        """
        import asyncio

        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._http.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Search request failed (attempt %d/%d): %s -- retrying in %.1fs",
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
                    "Search transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Search request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "WebSearchClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
