"""
Async Matter smart-home bridge client for the J.A.R.V.I.S. system.

Provides device discovery, state inspection, and control via an HTTP bridge
that communicates with a local Matter controller service.  The Matter
protocol itself is handled by the controller; this client speaks a simple
REST API to that bridge.

All HTTP communication is performed through *httpx* for seamless
integration with asyncio-based servers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.matter")

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


class MatterClient:
    """
    Async HTTP client for a Matter controller bridge service.

    The Matter controller runs as a separate process (e.g.
    ``python-matter-server``) and exposes a REST API.  This client wraps
    that API with retry logic and structured responses.
    """

    def __init__(
        self,
        controller_url: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        base_url = controller_url or settings.MATTER_CONTROLLER_URL

        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            headers={"Content-Type": "application/json"},
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def discover_devices(self) -> list[dict[str, Any]]:
        """
        Discover Matter devices visible to the controller.

        Returns
        -------
        list[dict]
            Each dict contains ``device_id``, ``name``, ``device_type``,
            ``room``, ``is_online``, and ``state``.
        """
        data = await self._request("GET", "/api/devices")
        devices = data.get("devices", data if isinstance(data, list) else [])

        parsed: list[dict[str, Any]] = []
        for dev in devices:
            parsed.append(self._parse_device(dev))

        logger.info("Discovered %d Matter device(s)", len(parsed))
        return parsed

    async def get_device(self, device_id: str) -> dict[str, Any]:
        """
        Get the current state of a specific device.

        Parameters
        ----------
        device_id:
            The device identifier known to the Matter controller.

        Returns
        -------
        dict
            Device info including ``device_id``, ``name``, ``device_type``,
            ``room``, ``is_online``, and ``state``.
        """
        data = await self._request("GET", f"/api/devices/{device_id}")
        return self._parse_device(data)

    async def control_device(
        self,
        device_id: str,
        command: str,
        params: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Send a control command to a device.

        Parameters
        ----------
        device_id:
            The device identifier.
        command:
            Command string, e.g. ``"on"``, ``"off"``, ``"set_brightness"``,
            ``"set_temperature"``, ``"lock"``, ``"unlock"``, ``"set_color"``.
        params:
            Optional command parameters (e.g. ``{"brightness": 80}``).

        Returns
        -------
        bool
            ``True`` if the command was accepted by the controller.
        """
        payload: dict[str, Any] = {
            "device_id": device_id,
            "command": command,
        }
        if params:
            payload["params"] = params

        try:
            data = await self._request("POST", f"/api/devices/{device_id}/command", json=payload)
            success = data.get("success", data.get("status") == "ok")
            if success:
                logger.info(
                    "Device command executed: device_id=%s command=%s params=%s",
                    device_id,
                    command,
                    params,
                )
            else:
                logger.warning(
                    "Device command rejected: device_id=%s command=%s error=%s",
                    device_id,
                    command,
                    data.get("error", "unknown"),
                )
            return bool(success)
        except Exception as exc:
            logger.error(
                "Failed to control device %s: %s",
                device_id,
                exc,
            )
            return False

    async def list_scenes(self) -> list[dict[str, Any]]:
        """
        List all configured scenes from the Matter controller.

        Returns
        -------
        list[dict]
            Each dict contains ``scene_id``, ``name``, ``description``,
            and ``devices`` (list of device actions).
        """
        data = await self._request("GET", "/api/scenes")
        scenes = data.get("scenes", data if isinstance(data, list) else [])

        parsed: list[dict[str, Any]] = []
        for scene in scenes:
            parsed.append({
                "scene_id": scene.get("id", scene.get("scene_id", "")),
                "name": scene.get("name", "Unnamed Scene"),
                "description": scene.get("description", ""),
                "devices": scene.get("devices", []),
                "is_active": scene.get("is_active", False),
            })

        return parsed

    async def activate_scene(self, scene_id: str) -> bool:
        """
        Activate a scene, sending all configured device commands.

        Parameters
        ----------
        scene_id:
            The scene identifier.

        Returns
        -------
        bool
            ``True`` if the scene was activated successfully.
        """
        try:
            data = await self._request(
                "POST",
                f"/api/scenes/{scene_id}/activate",
            )
            success = data.get("success", data.get("status") == "ok")
            if success:
                logger.info("Scene activated: scene_id=%s", scene_id)
            else:
                logger.warning(
                    "Scene activation failed: scene_id=%s error=%s",
                    scene_id,
                    data.get("error", "unknown"),
                )
            return bool(success)
        except Exception as exc:
            logger.error("Failed to activate scene %s: %s", scene_id, exc)
            return False

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
        Execute a request to the Matter controller bridge with retries
        for transient failures.
        """
        import asyncio

        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._http.request(
                    method,
                    path,
                    json=json,
                    params=params,
                )
                response.raise_for_status()

                # Some endpoints may return empty bodies (204)
                if response.status_code == 204 or not response.content:
                    return {"success": True}

                return response.json()

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = exc
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Matter request failed (attempt %d/%d): %s -- retrying in %.1fs",
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
                    "Matter transport error (attempt %d/%d): %s -- retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Matter request failed after {_MAX_RETRIES} retries"
        ) from last_exc

    # ── Parsing Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_device(data: dict[str, Any]) -> dict[str, Any]:
        """Extract useful fields from a Matter controller device resource."""
        return {
            "device_id": data.get("id", data.get("device_id", "")),
            "name": data.get("name", "Unknown Device"),
            "device_type": data.get("type", data.get("device_type", "unknown")),
            "room": data.get("room", data.get("location", "")),
            "is_online": data.get("is_online", data.get("online", True)),
            "state": data.get("state", {}),
            "manufacturer": data.get("manufacturer", ""),
            "model": data.get("model", ""),
        }

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "MatterClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
