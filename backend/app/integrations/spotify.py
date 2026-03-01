"""
Async Spotify client for the J.A.R.V.I.S. system.

Provides playback status, track search, and personalised
recommendations via the Spotify Web API.  Authentication uses the
OAuth 2.0 refresh-token flow so the client can maintain long-lived
access without user interaction.

All HTTP communication is performed through *httpx* for seamless
integration with asyncio-based servers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.spotify")

# API base URLs
_SPOTIFY_API_URL = "https://api.spotify.com/v1"
_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0  # seconds


class SpotifyClient:
    """
    Async Spotify Web API client with automatic token refresh.

    Requires ``SPOTIFY_CLIENT_ID``, ``SPOTIFY_CLIENT_SECRET``, and
    ``SPOTIFY_REFRESH_TOKEN`` in settings.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self._client_id = client_id or settings.SPOTIFY_CLIENT_ID
        self._client_secret = client_secret or settings.SPOTIFY_CLIENT_SECRET
        self._refresh_token = refresh_token or settings.SPOTIFY_REFRESH_TOKEN

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
        )

    # -- Authentication -------------------------------------------------------

    async def _ensure_access_token(self) -> str:
        """
        Return a valid access token, refreshing it if necessary.

        Uses the OAuth 2.0 *refresh_token* grant type so that
        long-running server processes never need browser interaction.
        """
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        if not self._client_id or not self._client_secret or not self._refresh_token:
            raise RuntimeError(
                "Spotify credentials not configured.  Set SPOTIFY_CLIENT_ID, "
                "SPOTIFY_CLIENT_SECRET, and SPOTIFY_REFRESH_TOKEN in settings."
            )

        logger.info("Refreshing Spotify access token")
        response = await self._http.post(
            _SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        self._token_expires_at = time.time() + token_data.get("expires_in", 3600)

        # If the API returned a new refresh token, update it in memory
        if "refresh_token" in token_data:
            self._refresh_token = token_data["refresh_token"]

        return self._access_token  # type: ignore[return-value]

    async def _auth_headers(self) -> dict[str, str]:
        """Build Authorization headers with a valid Bearer token."""
        token = await self._ensure_access_token()
        return {"Authorization": f"Bearer {token}"}

    # -- Public API -----------------------------------------------------------

    async def get_currently_playing(self) -> dict[str, Any]:
        """
        Fetch the user's currently-playing track.

        Returns
        -------
        dict
            Normalised track info with ``is_playing``, ``track``,
            ``artist``, ``album``, ``progress_ms``, ``duration_ms``,
            ``url``, ``image_url``.  If nothing is playing,
            ``is_playing`` is ``False``.
        """
        headers = await self._auth_headers()

        try:
            data = await self._request(
                "GET",
                f"{_SPOTIFY_API_URL}/me/player/currently-playing",
                headers=headers,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 204:
                return {"is_playing": False, "message": "Nothing is currently playing."}
            raise

        if not data:
            return {"is_playing": False, "message": "Nothing is currently playing."}

        item = data.get("item", {})
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
        images = item.get("album", {}).get("images", [])

        return {
            "is_playing": data.get("is_playing", False),
            "track": item.get("name", "Unknown"),
            "artist": artists,
            "album": item.get("album", {}).get("name", ""),
            "progress_ms": data.get("progress_ms", 0),
            "duration_ms": item.get("duration_ms", 0),
            "url": item.get("external_urls", {}).get("spotify", ""),
            "image_url": images[0]["url"] if images else "",
        }

    async def search_tracks(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search Spotify for tracks matching a query.

        Parameters
        ----------
        query:
            Free-text search query.
        limit:
            Maximum number of results (max 50).

        Returns
        -------
        list[dict]
            Each dict contains ``name``, ``artist``, ``album``,
            ``url``, ``duration_ms``, ``image_url``, and ``uri``.
        """
        headers = await self._auth_headers()

        data = await self._request(
            "GET",
            f"{_SPOTIFY_API_URL}/search",
            params={
                "q": query,
                "type": "track",
                "limit": min(limit, 50),
            },
            headers=headers,
        )

        results: list[dict[str, Any]] = []
        for item in data.get("tracks", {}).get("items", []):
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
            images = item.get("album", {}).get("images", [])
            results.append({
                "name": item.get("name", ""),
                "artist": artists,
                "album": item.get("album", {}).get("name", ""),
                "url": item.get("external_urls", {}).get("spotify", ""),
                "duration_ms": item.get("duration_ms", 0),
                "image_url": images[0]["url"] if images else "",
                "uri": item.get("uri", ""),
            })

        return results

    async def get_recommendations(
        self,
        seed_tracks: Optional[list[str]] = None,
        seed_artists: Optional[list[str]] = None,
        seed_genres: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get personalised track recommendations.

        At least one seed (tracks, artists, or genres) must be provided.
        The total number of seeds across all three categories cannot
        exceed 5.

        Parameters
        ----------
        seed_tracks:
            List of Spotify track IDs.
        seed_artists:
            List of Spotify artist IDs.
        seed_genres:
            List of genre names (e.g. ``["pop", "rock"]``).
        limit:
            Maximum number of recommendations (max 100).

        Returns
        -------
        list[dict]
            Same structure as :meth:`search_tracks`.
        """
        headers = await self._auth_headers()

        params: dict[str, Any] = {"limit": min(limit, 100)}
        if seed_tracks:
            params["seed_tracks"] = ",".join(seed_tracks[:5])
        if seed_artists:
            params["seed_artists"] = ",".join(seed_artists[:5])
        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])

        if not any(k.startswith("seed_") for k in params):
            return []

        data = await self._request(
            "GET",
            f"{_SPOTIFY_API_URL}/recommendations",
            params=params,
            headers=headers,
        )

        results: list[dict[str, Any]] = []
        for item in data.get("tracks", []):
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
            images = item.get("album", {}).get("images", [])
            results.append({
                "name": item.get("name", ""),
                "artist": artists,
                "album": item.get("album", {}).get("name", ""),
                "url": item.get("external_urls", {}).get("spotify", ""),
                "duration_ms": item.get("duration_ms", 0),
                "image_url": images[0]["url"] if images else "",
                "uri": item.get("uri", ""),
            })

        return results

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

                # Spotify returns 204 No Content for some endpoints
                if response.status_code == 204:
                    return {}

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                # If we get a 401, try refreshing the token once
                if exc.response.status_code == 401 and attempt == 0:
                    logger.info("Spotify token expired -- refreshing and retrying")
                    self._access_token = None
                    self._token_expires_at = 0.0
                    new_headers = await self._auth_headers()
                    if headers:
                        headers.update(new_headers)
                    else:
                        headers = new_headers
                    continue

                if exc.response.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = exc
                    # Spotify sends Retry-After header on 429
                    retry_after = exc.response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Spotify request failed (attempt %d/%d): %s -- retrying in %.1fs",
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
                    "Spotify transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Spotify request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # -- Lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "SpotifyClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
