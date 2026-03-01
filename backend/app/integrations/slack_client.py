"""Slack Web API client — channels, messages, search."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.slack")

_BASE_URL = "https://slack.com/api"


class SlackClient:
    """Async client for the Slack Web API."""

    def __init__(self, bot_token: str | None = None) -> None:
        self._token = bot_token or settings.SLACK_BOT_TOKEN

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def list_channels(self, limit: int = 20) -> list[dict[str, Any]]:
        """List public channels the bot has access to."""
        if not self._token:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/conversations.list",
                headers=self._headers(),
                params={"limit": limit, "types": "public_channel,private_channel"},
            )
            data = resp.json()
        if not data.get("ok"):
            logger.warning("Slack channels.list failed: %s", data.get("error"))
            return []
        return [
            {"id": ch["id"], "name": ch.get("name", ""), "topic": ch.get("topic", {}).get("value", "")}
            for ch in data.get("channels", [])
        ]

    async def read_messages(
        self,
        channel: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Read recent messages from a channel."""
        if not self._token:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/conversations.history",
                headers=self._headers(),
                params={"channel": channel, "limit": limit},
            )
            data = resp.json()
        if not data.get("ok"):
            logger.warning("Slack conversations.history failed: %s", data.get("error"))
            return []
        return [
            {
                "user": m.get("user", ""),
                "text": m.get("text", ""),
                "ts": m.get("ts", ""),
            }
            for m in data.get("messages", [])
        ]

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> dict[str, Any]:
        """Post a message to a channel."""
        if not self._token:
            return {"error": "Slack is not configured (SLACK_BOT_TOKEN missing)."}
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_BASE_URL}/chat.postMessage",
                headers=self._headers(),
                json=payload,
            )
            data = resp.json()

        if not data.get("ok"):
            return {"error": data.get("error", "Unknown error")}
        return {
            "channel": data.get("channel", channel),
            "ts": data.get("ts", ""),
            "ok": True,
        }

    async def search_messages(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        """Search messages across all channels."""
        if not self._token:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/search.messages",
                headers=self._headers(),
                params={"query": query, "count": count},
            )
            data = resp.json()
        if not data.get("ok"):
            logger.warning("Slack search failed: %s", data.get("error"))
            return []
        matches = data.get("messages", {}).get("matches", [])
        return [
            {
                "text": m.get("text", ""),
                "channel": m.get("channel", {}).get("name", ""),
                "user": m.get("username", ""),
                "ts": m.get("ts", ""),
                "permalink": m.get("permalink", ""),
            }
            for m in matches
        ]
