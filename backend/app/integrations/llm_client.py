"""Backward-compatible re-export of the OpenAI LLM client.

The monolithic ``LLMClient`` has been replaced by a multi-provider system
in :mod:`app.integrations.llm`.  This module re-exports ``OpenAIClient``
as ``LLMClient`` so that existing imports continue to work.
"""

from app.integrations.llm.openai_client import OpenAIClient as LLMClient  # noqa: F401
from app.integrations.llm.base import BaseLLMClient  # noqa: F401
from app.integrations.llm.factory import get_llm_client  # noqa: F401

__all__ = ["LLMClient", "BaseLLMClient", "get_llm_client"]
