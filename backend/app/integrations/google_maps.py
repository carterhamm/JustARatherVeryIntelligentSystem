"""Google Maps Platform API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.google_maps")

_BASE_URL = "https://maps.googleapis.com/maps/api"


class GoogleMapsClient:
    """Async client for Google Maps Platform APIs."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.GOOGLE_MAPS_API_KEY

    async def geocode(self, address: str) -> dict[str, Any]:
        """Convert an address to coordinates."""
        return await self._request("/geocode/json", address=address)

    async def reverse_geocode(self, lat: float, lng: float) -> dict[str, Any]:
        """Convert coordinates to an address."""
        return await self._request("/geocode/json", latlng=f"{lat},{lng}")

    async def directions(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
    ) -> dict[str, Any]:
        """Get directions between two locations."""
        return await self._request(
            "/directions/json",
            origin=origin,
            destination=destination,
            mode=mode,
        )

    async def places_search(
        self,
        query: str,
        location: str | None = None,
        radius: int = 5000,
    ) -> dict[str, Any]:
        """Search for places by text query."""
        params: dict[str, Any] = {"query": query, "radius": radius}
        if location:
            params["location"] = location
        return await self._request("/place/textsearch/json", **params)

    async def distance_matrix(
        self,
        origins: str,
        destinations: str,
        mode: str = "driving",
    ) -> dict[str, Any]:
        """Get travel distance and time for multiple origins/destinations."""
        return await self._request(
            "/distancematrix/json",
            origins=origins,
            destinations=destinations,
            mode=mode,
        )

    async def _request(self, endpoint: str, **params: Any) -> dict[str, Any]:
        if not self._api_key:
            return {"error": "Google Maps API is not configured (GOOGLE_MAPS_API_KEY missing)."}

        query_params = {"key": self._api_key, **params}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{_BASE_URL}{endpoint}", params=query_params)
            response.raise_for_status()
            data = response.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS", None):
            return {"error": data.get("error_message", data.get("status", "Unknown error"))}

        return data
