"""Camera service — proxy to Mac Mini camera daemon for RTSP/ONVIF/vision."""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.camera")


class CameraService:
    """Proxy layer to the Mac Mini camera daemon.

    The daemon runs on the local network with direct RTSP/ONVIF access
    to the camera. This service forwards requests from Railway → Mac Mini
    via the Cloudflare tunnel (Caddy Bearer Auth).
    """

    @staticmethod
    def _base_url() -> str:
        url = settings.CAMERA_PROXY_URL
        if not url:
            raise RuntimeError("CAMERA_PROXY_URL not configured")
        return url.rstrip("/")

    @staticmethod
    def _headers() -> dict[str, str]:
        """Build auth headers for the Caddy proxy."""
        headers: dict[str, str] = {}
        token = settings.CAMERA_AUTH_TOKEN or settings.MAC_MINI_AGENT_KEY
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    async def get_status() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{CameraService._base_url()}/status",
                headers=CameraService._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def get_snapshot() -> bytes:
        """Get a JPEG snapshot from the camera."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{CameraService._base_url()}/snapshot",
                headers=CameraService._headers(),
            )
            resp.raise_for_status()
            return resp.content

    @staticmethod
    async def get_snapshot_base64() -> str:
        data = await CameraService.get_snapshot()
        return base64.b64encode(data).decode()

    @staticmethod
    async def ptz_command(
        action: str, speed: float = 0.5, duration: float = 0.5
    ) -> dict[str, Any]:
        """Send PTZ command: left, right, up, down, home, stop."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{CameraService._base_url()}/ptz/{action}",
                json={"speed": speed, "duration": duration},
                headers=CameraService._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def get_gestures() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{CameraService._base_url()}/gestures",
                headers=CameraService._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def analyze_frame(prompt: str = "") -> str:
        """Capture a frame and analyze it with Gemini vision."""
        try:
            snapshot_bytes = await CameraService.get_snapshot()
        except Exception as exc:
            return f"Camera unavailable: {exc}"

        analysis_prompt = prompt or (
            "Describe what you see in this security camera frame. "
            "Note any people, their actions/gestures, objects, and activity."
        )

        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = await model.generate_content_async(
                [
                    analysis_prompt,
                    {"mime_type": "image/jpeg", "data": base64.b64encode(snapshot_bytes).decode()},
                ]
            )
            return response.text
        except Exception as exc:
            logger.exception("Vision analysis failed")
            return f"Vision analysis error: {exc}"

    @staticmethod
    async def stream_proxy():
        """Async generator that proxies MJPEG stream from the daemon."""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{CameraService._base_url()}/stream",
                headers=CameraService._headers(),
            ) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    yield chunk
