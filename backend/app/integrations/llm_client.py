"""Backward-compatible re-export of the default LLM client.

The monolithic ``LLMClient`` has been replaced by a multi-provider system
in :mod:`app.integrations.llm`.  This module re-exports ``ClaudeClient``
as ``LLMClient`` so that existing imports continue to work.
"""

from app.integrations.llm.claude_client import ClaudeClient as LLMClient  # noqa: F401
from app.integrations.llm.base import BaseLLMClient  # noqa: F401
from app.integrations.llm.factory import get_llm_client  # noqa: F401

__all__ = ["LLMClient", "BaseLLMClient", "get_llm_client"]
