"""
Async weather client for the J.A.R.V.I.S. system.

Fetches current conditions and multi-day forecasts from the
OpenWeatherMap API.  All HTTP communication is performed through
*httpx* for seamless integration with asyncio-based servers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.weather")

# API base URL
_OWM_API_URL = "https://api.openweathermap.org/data/2.5"

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0  # seconds


class WeatherClient:
    """
    Async weather client backed by OpenWeatherMap.

    Provides current weather conditions and multi-day forecasts.
    Supports lookup by city name or geographic coordinates.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self._api_key = api_key or settings.WEATHER_API_KEY
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
        )

    # -- Public API -----------------------------------------------------------

    async def get_current(
        self,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        units: str = "metric",
    ) -> dict[str, Any]:
        """
        Fetch current weather conditions.

        Parameters
        ----------
        city:
            City name (e.g. ``"London"`` or ``"London,GB"``).
        lat:
            Latitude (used when *city* is not provided).
        lon:
            Longitude (used when *city* is not provided).
        units:
            Unit system -- ``"metric"``, ``"imperial"``, or ``"standard"``.

        Returns
        -------
        dict
            Normalised weather data with keys: ``location``, ``temperature``,
            ``feels_like``, ``humidity``, ``description``, ``wind_speed``,
            ``wind_direction``, ``pressure``, ``visibility``, ``clouds``,
            ``icon``, ``dt``.
        """
        if not self._api_key:
            logger.warning("No WEATHER_API_KEY configured -- returning empty result")
            return {"error": "No WEATHER_API_KEY configured."}

        params: dict[str, Any] = {
            "appid": self._api_key,
            "units": units,
        }
        if city:
            params["q"] = city
        elif lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        else:
            return {"error": "Provide either 'city' or both 'lat' and 'lon'."}

        data = await self._request("GET", f"{_OWM_API_URL}/weather", params=params)
        return self._normalise_current(data, units)

    async def get_forecast(
        self,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        days: int = 5,
        units: str = "metric",
    ) -> dict[str, Any]:
        """
        Fetch a multi-day weather forecast (3-hour intervals from OWM).

        Parameters
        ----------
        city:
            City name.
        lat / lon:
            Geographic coordinates (used when *city* is not provided).
        days:
            Number of forecast days (max 5 on the free tier).
        units:
            Unit system.

        Returns
        -------
        dict
            Contains ``location`` and a ``forecast`` list of daily
            summaries.
        """
        if not self._api_key:
            logger.warning("No WEATHER_API_KEY configured -- returning empty result")
            return {"error": "No WEATHER_API_KEY configured."}

        params: dict[str, Any] = {
            "appid": self._api_key,
            "units": units,
            "cnt": min(days, 5) * 8,  # 8 intervals per day (3-hour steps)
        }
        if city:
            params["q"] = city
        elif lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        else:
            return {"error": "Provide either 'city' or both 'lat' and 'lon'."}

        data = await self._request("GET", f"{_OWM_API_URL}/forecast", params=params)
        return self._normalise_forecast(data, units, days)

    # -- Normalisation helpers ------------------------------------------------

    @staticmethod
    def _unit_label(units: str) -> str:
        return {"metric": "C", "imperial": "F"}.get(units, "K")

    def _normalise_current(self, data: dict[str, Any], units: str) -> dict[str, Any]:
        """Flatten the raw OWM current-weather response."""
        main = data.get("main", {})
        wind = data.get("wind", {})
        weather = data.get("weather", [{}])[0]
        unit = self._unit_label(units)

        return {
            "location": data.get("name", "Unknown"),
            "country": data.get("sys", {}).get("country", ""),
            "temperature": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "temp_min": main.get("temp_min"),
            "temp_max": main.get("temp_max"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
            "description": weather.get("description", ""),
            "icon": weather.get("icon", ""),
            "wind_speed": wind.get("speed"),
            "wind_direction": wind.get("deg"),
            "visibility": data.get("visibility"),
            "clouds": data.get("clouds", {}).get("all"),
            "dt": data.get("dt"),
            "units": unit,
        }

    def _normalise_forecast(
        self,
        data: dict[str, Any],
        units: str,
        days: int,
    ) -> dict[str, Any]:
        """Group the 3-hour OWM forecast into daily summaries."""
        city = data.get("city", {})
        unit = self._unit_label(units)

        # Group entries by date
        daily: dict[str, list[dict[str, Any]]] = {}
        for entry in data.get("list", []):
            date_str = entry.get("dt_txt", "")[:10]  # YYYY-MM-DD
            daily.setdefault(date_str, []).append(entry)

        forecast_days: list[dict[str, Any]] = []
        for date_str, entries in list(daily.items())[:days]:
            temps = [e["main"]["temp"] for e in entries if "main" in e]
            descriptions = [
                e["weather"][0]["description"]
                for e in entries
                if e.get("weather")
            ]
            humidities = [e["main"]["humidity"] for e in entries if "main" in e]
            wind_speeds = [e["wind"]["speed"] for e in entries if "wind" in e]

            # Pick the most frequent description
            desc_counts: dict[str, int] = {}
            for d in descriptions:
                desc_counts[d] = desc_counts.get(d, 0) + 1
            dominant_desc = max(desc_counts, key=desc_counts.get) if desc_counts else ""  # type: ignore[arg-type]

            forecast_days.append({
                "date": date_str,
                "temp_min": round(min(temps), 1) if temps else None,
                "temp_max": round(max(temps), 1) if temps else None,
                "temp_avg": round(sum(temps) / len(temps), 1) if temps else None,
                "humidity_avg": round(sum(humidities) / len(humidities)) if humidities else None,
                "wind_speed_avg": round(sum(wind_speeds) / len(wind_speeds), 1) if wind_speeds else None,
                "description": dominant_desc,
            })

        return {
            "location": city.get("name", "Unknown"),
            "country": city.get("country", ""),
            "units": unit,
            "forecast": forecast_days,
        }

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
                        "Weather request failed (attempt %d/%d): %s -- retrying in %.1fs",
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
                    "Weather transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Weather request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # -- Lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "WeatherClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
