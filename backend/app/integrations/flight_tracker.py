"""AviationStack flight tracking API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.flight_tracker")

_BASE_URL = "https://api.aviationstack.com/v1"


class FlightTrackerClient:
    """Async client for the AviationStack API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.AVIATIONSTACK_API_KEY

    async def track_flight(self, flight_iata: str) -> dict[str, Any]:
        """Track a flight by its IATA code (e.g., AA100)."""
        return await self._request("flights", flight_iata=flight_iata)

    async def search_flights(
        self,
        dep_iata: str | None = None,
        arr_iata: str | None = None,
        airline_iata: str | None = None,
    ) -> dict[str, Any]:
        """Search for flights by departure/arrival airport or airline."""
        params: dict[str, str] = {}
        if dep_iata:
            params["dep_iata"] = dep_iata
        if arr_iata:
            params["arr_iata"] = arr_iata
        if airline_iata:
            params["airline_iata"] = airline_iata
        return await self._request("flights", **params)

    async def get_airport_info(self, iata_code: str) -> dict[str, Any]:
        """Get airport information by IATA code."""
        return await self._request("airports", iata_code=iata_code)

    async def _request(self, endpoint: str, **params: Any) -> dict[str, Any]:
        if not self._api_key:
            return {"error": "AviationStack API is not configured (AVIATIONSTACK_API_KEY missing)."}

        query_params = {"access_key": self._api_key, **params}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{_BASE_URL}/{endpoint}", params=query_params)
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            return {"error": data["error"].get("message", "Unknown error")}

        return data
