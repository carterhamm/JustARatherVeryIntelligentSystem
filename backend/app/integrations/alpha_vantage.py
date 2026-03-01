"""Alpha Vantage financial data API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.alpha_vantage")

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    """Async client for the Alpha Vantage API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.ALPHA_VANTAGE_API_KEY

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get a real-time stock quote."""
        return await self._request("GLOBAL_QUOTE", symbol=symbol)

    async def search_symbol(self, keywords: str) -> dict[str, Any]:
        """Search for a stock symbol by keywords."""
        return await self._request("SYMBOL_SEARCH", keywords=keywords)

    async def get_daily(self, symbol: str, compact: bool = True) -> dict[str, Any]:
        """Get daily time series data."""
        return await self._request(
            "TIME_SERIES_DAILY",
            symbol=symbol,
            outputsize="compact" if compact else "full",
        )

    async def _request(self, function: str, **params: Any) -> dict[str, Any]:
        if not self._api_key:
            return {"error": "Alpha Vantage API is not configured (ALPHA_VANTAGE_API_KEY missing)."}

        query_params = {
            "function": function,
            "apikey": self._api_key,
            **params,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_BASE_URL, params=query_params)
            response.raise_for_status()
            data = response.json()

        if "Error Message" in data:
            return {"error": data["Error Message"]}
        if "Note" in data:
            return {"error": data["Note"]}

        return data
