"""Wolfram Alpha Full Results API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.wolfram")

_BASE_URL = "https://api.wolframalpha.com/v2/query"


class WolframClient:
    """Async client for Wolfram Alpha Full Results API."""

    def __init__(self, app_id: str | None = None) -> None:
        self._app_id = app_id or settings.WOLFRAM_APP_ID

    async def query(self, input_text: str, **kwargs: Any) -> dict[str, Any]:
        """Send a query to Wolfram Alpha and return parsed results."""
        if not self._app_id:
            return {"error": "Wolfram Alpha API is not configured (WOLFRAM_APP_ID missing)."}

        params = {
            "input": input_text,
            "appid": self._app_id,
            "format": "plaintext",
            "output": "json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        query_result = data.get("queryresult", {})
        if not query_result.get("success"):
            return {
                "success": False,
                "error": query_result.get("error", {}).get("msg", "Query failed"),
                "suggestions": [
                    tip.get("text", "")
                    for tip in query_result.get("tips", {}).get("tip", [])
                ],
            }

        pods: list[dict[str, str]] = []
        for pod in query_result.get("pods", []):
            title = pod.get("title", "")
            subpod_texts = []
            for subpod in pod.get("subpods", []):
                plaintext = subpod.get("plaintext", "")
                if plaintext:
                    subpod_texts.append(plaintext)
            if subpod_texts:
                pods.append({"title": title, "text": "\n".join(subpod_texts)})

        return {
            "success": True,
            "input": input_text,
            "pods": pods,
        }
