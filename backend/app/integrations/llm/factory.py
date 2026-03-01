"""LLM client factory — resolves a provider enum to a singleton client."""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.integrations.llm.base import BaseLLMClient, LLMProvider

logger = logging.getLogger("jarvis.llm.factory")

# Singleton cache keyed by provider
_client_cache: dict[LLMProvider, BaseLLMClient] = {}


def get_llm_client(provider: Optional[str | LLMProvider] = None) -> BaseLLMClient:
    """Return a (cached) LLM client for the given provider.

    If *provider* is ``None``, the ``DEFAULT_LLM_PROVIDER`` setting is used.
    """
    if provider is None:
        provider = settings.DEFAULT_LLM_PROVIDER

    # Normalize to enum
    if isinstance(provider, str):
        try:
            provider_enum = LLMProvider(provider.lower())
        except ValueError:
            logger.warning("Unknown provider '%s'; falling back to OpenAI", provider)
            provider_enum = LLMProvider.OPENAI
    else:
        provider_enum = provider

    if provider_enum in _client_cache:
        return _client_cache[provider_enum]

    client = _build_client(provider_enum)
    _client_cache[provider_enum] = client
    logger.info("Created LLM client for provider: %s", provider_enum.value)
    return client


def _build_client(provider: LLMProvider) -> BaseLLMClient:
    """Instantiate a fresh client for the given provider."""
    if provider == LLMProvider.OPENAI:
        from app.integrations.llm.openai_client import OpenAIClient

        return OpenAIClient(api_key=settings.OPENAI_API_KEY)

    elif provider == LLMProvider.CLAUDE:
        from app.integrations.llm.claude_client import ClaudeClient

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        return ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)

    elif provider == LLMProvider.GEMINI:
        from app.integrations.llm.gemini_client import GeminiClient

        if not settings.GOOGLE_GEMINI_API_KEY:
            raise ValueError("GOOGLE_GEMINI_API_KEY is not configured")
        return GeminiClient(api_key=settings.GOOGLE_GEMINI_API_KEY)

    elif provider == LLMProvider.STARK_PROTOCOL:
        from app.integrations.llm.stark_client import StarkProtocolClient

        if not settings.STARK_PROTOCOL_ENABLED:
            raise ValueError("Stark Protocol is not enabled")
        return StarkProtocolClient(base_url=settings.STARK_PROTOCOL_URL)

    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def clear_client_cache() -> None:
    """Clear the singleton cache (useful for testing)."""
    _client_cache.clear()
