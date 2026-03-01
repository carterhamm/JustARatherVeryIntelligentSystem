"""Perplexity API client — uses OpenAI-compatible endpoint."""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger("jarvis.integrations.perplexity")


class PerplexityClient:
    """Async client for the Perplexity Sonar API (OpenAI-compatible)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.PERPLEXITY_API_KEY
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.perplexity.ai",
            timeout=60.0,
        ) if self._api_key else None

    async def research(
        self,
        query: str,
        model: str = "sonar",
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Perform a research query using Perplexity's search-augmented LLM."""
        if not self._client:
            return {"error": "Perplexity API is not configured (PERPLEXITY_API_KEY missing)."}

        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant. Provide comprehensive, "
                        "well-sourced answers with citations."
                    ),
                },
                {"role": "user", "content": query},
            ],
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        return {
            "content": choice.message.content or "",
            "model": response.model,
            "citations": getattr(response, "citations", []),
        }
