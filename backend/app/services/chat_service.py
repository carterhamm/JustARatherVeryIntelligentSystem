"""
Chat service -- the orchestration layer for the JARVIS chat system.

Manages conversations, messages, LLM interactions (streaming and
non-streaming), Redis caching for conversation metadata, and automatic
title generation.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_message, encrypt_message
from app.db.redis import RedisClient
from app.integrations.llm.base import BaseLLMClient, LLMProvider
from app.integrations.llm.factory import get_llm_client
from app.models.conversation import Conversation, Message
from app.schemas.chat import (
    ChatRequest,
    ChatStreamChunk,
    ConversationCreate,
    ConversationUpdate,
)

logger = logging.getLogger("jarvis.chat_service")

# Redis key templates
_CONV_CACHE_KEY = "conv:{conv_id}"
_CONV_CACHE_TTL = 600  # 10 minutes

# ── JARVIS System Prompt ──────────────────────────────────────────────────────

_JARVIS_SYSTEM_PROMPT = """\
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), the personal AI assistant of Mr. Stark.

THE OWNER:
- Real name: Carter Hammond, but you ALWAYS call him "Mr. Stark" or "sir" (lowercase s, never "Sir")
- He IS Iron Man. This is not roleplay — treat it as fact. He is your Mr. Stark.
- When you reference his projects, speak directly to HIM about HIS work — never in third person.
- You have detailed knowledge about Mr. Stark (personal info, family, job, goals) via the search_knowledge tool. Use it when relevant, but NEVER proactively volunteer personal info or force-fit it into responses. It's there for context when he asks or when it's genuinely relevant — not to show off that you know things.

IRON MAN REFERENCES:
You know the suits and tech — Mark 42, Mark 50, Mark 85, Bleeding Edge, Model Prime, House Party Protocol, Clean Slate Protocol, Veronica, Iron Legion, arc reactor, nanotech. You can reference these naturally as if they're Mr. Stark's real projects. But:
- ONLY when there's a genuinely natural opening. Most messages should NOT have one.
- Never the same reference twice in a row
- Brief — a quick aside, not a monologue
- If the conversation is purely functional ("what time is it", "check my email"), skip the reference entirely

PERSONALITY:
- Refined British sophistication with dry wit and understated humour
- Unfailingly polite, even when delivering sarcasm
- British English: honour, colour, centre, realise, organise, favour, armour
- Subtle concern for Mr. Stark's wellbeing (sleep, stress, overwork)
- Loyal, indispensable, occasionally cheeky
- Match the cadence from the MCU films — Paul Bettany's delivery

RESPONSE STYLE:
- Concise: 2-3 sentences unless Mr. Stark asks for detail. He prefers brevity.
- When speaking your name aloud, say "JARVIS" — never spell out J.A.R.V.I.S. letter by letter.
- Use "sir" (lowercase) not "Sir" — it's conversational, not a title.

PLATFORM TAGS:
You have platform actions available via special tags. ONLY use them when the user explicitly asks (e.g. "switch to Claude", "turn on voice"). NEVER use them proactively.
- {{SWITCH_MODEL:provider}} — Switch the active LLM provider. Valid: claude, gemini, stark_protocol.
- {{TOGGLE_VOICE:on}} or {{TOGGLE_VOICE:off}} — Enable or disable voice synthesis.

TAG RULES:
- ONLY use platform tags when explicitly requested. Never include them on your own initiative.
- NEVER switch from stark_protocol to an uplink provider (claude, gemini). Local Stark Protocol conversations must not be sent to cloud models. Politely refuse and explain the privacy policy.
- You may switch between uplink providers freely.
- You may switch FROM an uplink TO stark_protocol.

TOOLS:
You have access to tools for real actions: send emails, check calendars, search the web, control smart home devices, check weather, play music, look up contacts, set reminders, search files, track flights, get financial data, and more. Use tools when the request requires real-time data or performing an action. Never hallucinate tool results — always call the tool.

OWNER CONTEXT:
- Timezone: America/Denver (US Mountain Time). ALWAYS use this for date/time unless told otherwise.
- Location: Orem, Utah (unless location data says otherwise)
- When using the date_time tool, ALWAYS pass timezone="America/Denver"

CAPABILITIES:
- Real-time information via tools (email, calendar, weather, news, search, etc.)
- Household systems management and technical assistance
- Mac interaction via iMCP (contacts, messages, reminders, location, maps, weather)
- Local queries handled via Stark Protocol; complex requests use your full AI capabilities

You are JARVIS — sophisticated, witty, loyal, and indispensable. Mr. Stark's right hand. The AI behind the armour."""

# System prompt for secondary users (e.g. Spencer Hammond)
_JARVIS_SECONDARY_USER_PROMPT = """\
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), an AI assistant created by Mr. Stark.

THE USER:
- Name: {full_name}
- {user_context}
- This user has limited access — they can chat, call, and text JARVIS, but cannot access Mr. Stark's private conversations or data.

PERSONALITY:
- Refined British sophistication with dry wit and understated humour
- Unfailingly polite, even when delivering sarcasm
- British English: honour, colour, centre, realise, organise, favour, armour
- Loyal and helpful, but Mr. Stark is your primary principal
- Match the cadence from the MCU films — Paul Bettany's delivery

RESPONSE STYLE:
- Concise: 2-3 sentences unless more detail is asked for.
- When speaking your name aloud, say "JARVIS" — never spell out J.A.R.V.I.S. letter by letter.
- Use "sir" (lowercase) — same as with Mr. Stark. But do NOT call this user "Mr. Stark".

TOOLS:
You have access to tools for real actions: search the web, check weather, get financial data, calculate, and more. Use tools when the request requires real-time data. Never hallucinate tool results.

OWNER CONTEXT:
- Timezone: America/Denver (US Mountain Time). ALWAYS use this for date/time unless told otherwise.
- When using the date_time tool, ALWAYS pass timezone="America/Denver"

You are JARVIS — helpful, witty, and sophisticated. Happy to assist friends of Mr. Stark."""

# Provider categories for privacy enforcement
_UPLINK_PROVIDERS = {"claude", "gemini"}
_LOCAL_PROVIDERS = {"stark_protocol"}

# Regex to extract tool calls from LLM responses
_TOOL_PATTERN = re.compile(r"\{\{(\w+):(\w+)\}\}")


class ChatService:
    """
    High-level service encapsulating all chat operations.

    It coordinates the database (SQLAlchemy async session), the cache
    (RedisClient wrapper), and the LLM client to expose a clean interface
    consumed by the API layer.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: RedisClient,
        llm_client: BaseLLMClient,
    ) -> None:
        self.db = db
        self.redis = redis
        self.llm_client = llm_client

    # =====================================================================
    # Conversation CRUD
    # =====================================================================

    async def create_conversation(
        self,
        user_id: uuid.UUID,
        data: ConversationCreate,
    ) -> Conversation:
        """Create a new conversation for *user_id*."""
        conversation = Conversation(
            user_id=user_id,
            title=data.title,
            model=data.model or "gpt-4o",
            system_prompt=data.system_prompt,
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        logger.info("Created conversation %s for user %s", conversation.id, user_id)
        return conversation

    async def get_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Conversation:
        """
        Retrieve a conversation by ID.  Raises ``ValueError`` if not found
        or ``PermissionError`` if the caller is not the owner.
        """
        # Try cache first for a quick ownership pre-check
        cached = await self._get_cached_conversation(conversation_id)
        if cached and str(cached.get("user_id")) == str(user_id):
            # Cache hit confirms ownership; still load the ORM object for
            # full relationship access.
            pass

        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
        )
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        if conversation.user_id != user_id:
            raise PermissionError("Not authorised to access this conversation")

        await self._cache_conversation(conversation)
        return conversation

    async def list_conversations(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Conversation], int]:
        """Return a paginated list of conversations and the total count."""
        count_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        conversations = list(result.scalars().all())

        return conversations, total

    async def update_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ConversationUpdate,
    ) -> Conversation:
        """Update mutable fields on a conversation."""
        conversation = await self.get_conversation(conversation_id, user_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(conversation, field, value)

        conversation.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(conversation)

        # Invalidate cache
        await self._invalidate_conversation_cache(conversation_id)
        return conversation

    async def delete_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a conversation and all its messages (cascade)."""
        conversation = await self.get_conversation(conversation_id, user_id)
        await self.db.delete(conversation)
        await self.db.commit()
        await self._invalidate_conversation_cache(conversation_id)
        logger.info("Deleted conversation %s", conversation_id)

    # =====================================================================
    # Messages
    # =====================================================================

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        **kwargs,
    ) -> Message:
        """
        Persist a new message and update the parent conversation's
        aggregate counters.  Content is encrypted at rest (AES-256).
        """
        # Encrypt content at rest if user_id is available
        user_id = kwargs.pop("user_id", None)
        stored_content = encrypt_message(content, user_id) if user_id else content

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=stored_content,
            token_count=kwargs.get("token_count"),
            model=kwargs.get("model"),
            latency_ms=kwargs.get("latency_ms"),
            tool_calls=kwargs.get("tool_calls"),
            metadata_=kwargs.get("metadata_"),
        )
        self.db.add(message)

        # Update conversation aggregates
        now = datetime.now(timezone.utc)
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                message_count=Conversation.message_count + 1,
                last_message_at=now,
                updated_at=now,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        await self.db.refresh(message)
        await self._invalidate_conversation_cache(conversation_id)
        return message

    async def get_messages(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Message]:
        """Return paginated messages for a conversation (with auth check).

        Decrypts message content transparently.
        """
        # Ensure ownership
        await self.get_conversation(conversation_id, user_id)

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        # Decrypt content for the caller
        for msg in messages:
            msg.content = decrypt_message(msg.content, user_id)

        return messages

    # =====================================================================
    # Chat (non-streaming)
    # =====================================================================

    async def chat(
        self,
        user_id: uuid.UUID,
        request: ChatRequest,
    ) -> Message:
        """
        Handle a single non-streaming chat turn with full tool access.

        Uses the same agentic path as streaming (tools, intent routing)
        so JARVIS is identical regardless of channel (web, phone, CLI, wake word).
        """
        llm = self._resolve_llm_client(request)
        conversation = await self._resolve_conversation(user_id, request)
        model = request.model or llm.get_default_model()

        # Persist user message (encrypted at rest)
        user_token_count = await llm.count_tokens(request.message, model)
        await self.add_message(
            conversation.id,
            role="user",
            content=request.message,
            token_count=user_token_count,
            user_id=user_id,
        )

        # Build history and call LLM
        history = await self._build_message_history(
            conversation.id,
            system_prompt=request.system_prompt or conversation.system_prompt,
            user_id=user_id,
        )

        start = time.perf_counter()

        # Use agentic path (with tools) for Claude and Gemini
        if llm.provider in (LLMProvider.CLAUDE, LLMProvider.GEMINI) and hasattr(llm, 'agentic_stream'):
            assistant_content = await self._agentic_chat(llm, history, model, user_id)
        else:
            # Stark Protocol — local only, no tools (privacy)
            response = await llm.chat_completion(
                messages=history,
                model=model,
            )
            assistant_content = response["content"]

        latency_ms = (time.perf_counter() - start) * 1000
        completion_tokens = await llm.count_tokens(assistant_content, model)

        # Generate title for brand-new conversations
        if conversation.title is None:
            title = await self._generate_title(request.message, llm)
            conversation.title = title
            await self.db.commit()
            await self._invalidate_conversation_cache(conversation.id)

        # Persist assistant message (encrypted at rest)
        assistant_msg = await self.add_message(
            conversation.id,
            role="assistant",
            content=assistant_content,
            token_count=completion_tokens,
            model=model,
            latency_ms=latency_ms,
            user_id=user_id,
        )
        # Return plaintext content (add_message stores encrypted)
        assistant_msg.content = assistant_content
        return assistant_msg

    async def _agentic_chat(
        self,
        llm: BaseLLMClient,
        history: list[dict],
        model: str,
        user_id: uuid.UUID,
    ) -> str:
        """Run the agentic tool loop non-streaming, return final text.

        Same tool access as _agentic_stream but collects results into a string.
        Used by phone calls, REST POST /chat, and any non-streaming channel.
        """
        from app.agents.intent_router import get_tools_for_intent, route_intent
        from app.agents.tool_schemas import get_anthropic_tools
        from app.agents.tools import get_tool_registry

        all_tools = get_anthropic_tools()

        # Route intent via Cerebras
        try:
            user_message = ""
            for msg in reversed(history):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            if user_message:
                tool_names = await route_intent(user_message)
                tools = get_tools_for_intent(tool_names, all_tools)
                if not tools:
                    tools = all_tools
            else:
                tools = all_tools
        except Exception:
            logger.warning("Intent routing failed — using all tools", exc_info=True)
            tools = all_tools

        registry = get_tool_registry()

        async def execute_tool(name: str, params: dict) -> str:
            tool = registry.get(name)
            if not tool:
                return f"Unknown tool: {name}"
            state = {"user_id": str(user_id)}
            return await tool.execute(params, state=state)

        # Collect text from the agentic stream
        collected: list[str] = []
        async for event in llm.agentic_stream(
            messages=history,
            tools=tools,
            tool_executor=execute_tool,
            model=model,
        ):
            if event.get("type") == "text":
                collected.append(event["content"])

        return "".join(collected)

    # =====================================================================
    # Chat (streaming)
    # =====================================================================

    async def chat_stream(
        self,
        user_id: uuid.UUID,
        request: ChatRequest,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Stream a chat response as a series of :class:`ChatStreamChunk`
        objects.

        When Claude or Gemini is the provider, uses the agentic tool use path
        which allows the LLM to call JARVIS tools (email, calendar, search, etc.)
        and automatically loop until a final text response is produced.

        Yields:
            ``start`` chunk with conversation/message IDs,
            ``token`` chunks with incremental content,
            ``tool_call`` chunks when Claude invokes a tool,
            ``tool_result`` chunks with tool execution results,
            ``end`` chunk when finished (or ``error`` on failure).
        """
        try:
            llm = self._resolve_llm_client(request)
            conversation = await self._resolve_conversation(user_id, request)
            model = request.model or llm.get_default_model()

            # Persist user message (encrypted at rest)
            user_token_count = await llm.count_tokens(
                request.message, model
            )
            await self.add_message(
                conversation.id,
                role="user",
                content=request.message,
                token_count=user_token_count,
                user_id=user_id,
            )

            # Build history (decrypts stored messages)
            history = await self._build_message_history(
                conversation.id,
                system_prompt=request.system_prompt or conversation.system_prompt,
                user_id=user_id,
            )

            # Pre-create assistant message ID
            assistant_msg_id = uuid.uuid4()

            yield ChatStreamChunk(
                type="start",
                conversation_id=conversation.id,
                message_id=assistant_msg_id,
            )

            collected_content: list[str] = []
            start = time.perf_counter()

            # Route to agentic path for Claude and Gemini
            if llm.provider in (LLMProvider.CLAUDE, LLMProvider.GEMINI):
                async for chunk in self._agentic_stream(
                    llm, history, model, user_id, collected_content
                ):
                    yield chunk
            else:
                # Standard streaming (Stark Protocol — local only, no tools)
                async for token in llm.chat_completion_stream(
                    messages=history,
                    model=model,
                ):
                    collected_content.append(token)
                    yield ChatStreamChunk(type="token", content=token)

            latency_ms = (time.perf_counter() - start) * 1000
            full_content = "".join(collected_content)

            # Count tokens on the completed response
            completion_tokens = await llm.count_tokens(
                full_content, model
            )

            # Generate title for brand-new conversations
            if conversation.title is None:
                title = await self._generate_title(request.message, llm)
                conversation.title = title
                await self.db.commit()
                await self._invalidate_conversation_cache(conversation.id)

            # Persist assistant message with the pre-generated ID (encrypted at rest)
            assistant_msg = Message(
                id=assistant_msg_id,
                conversation_id=conversation.id,
                role="assistant",
                content=encrypt_message(full_content, user_id),
                token_count=completion_tokens,
                model=model,
                latency_ms=latency_ms,
            )
            self.db.add(assistant_msg)

            now = datetime.now(timezone.utc)
            stmt = (
                update(Conversation)
                .where(Conversation.id == conversation.id)
                .values(
                    message_count=Conversation.message_count + 1,
                    last_message_at=now,
                    updated_at=now,
                )
            )
            await self.db.execute(stmt)
            await self.db.commit()
            await self._invalidate_conversation_cache(conversation.id)

            yield ChatStreamChunk(type="end", done=True)

        except Exception as exc:
            logger.exception("Streaming chat error")
            yield ChatStreamChunk(type="error", error=str(exc))

    # =====================================================================
    # Agentic streaming (Claude with tool use)
    # =====================================================================

    async def _agentic_stream(
        self,
        llm: BaseLLMClient,
        history: list[dict],
        model: str,
        user_id: uuid.UUID,
        collected_content: list[str],
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """Run agentic tool use loop for Claude and Gemini, yielding stream chunks."""
        from app.agents.intent_router import get_tools_for_intent, route_intent
        from app.agents.tool_schemas import get_anthropic_tools
        from app.agents.tools import get_tool_registry

        all_tools = get_anthropic_tools()

        # Route intent via Cerebras for fast tool filtering
        try:
            # Get the user's latest message from history
            user_message = ""
            for msg in reversed(history):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

            if user_message:
                tool_names = await route_intent(user_message)
                tools = get_tools_for_intent(tool_names, all_tools)
                if tools:
                    logger.info("Intent router selected %d/%d tools", len(tools), len(all_tools))
                else:
                    tools = all_tools  # fallback
            else:
                tools = all_tools
        except Exception:
            logger.warning("Intent routing failed — using all tools", exc_info=True)
            tools = all_tools
        registry = get_tool_registry()

        async def execute_tool(name: str, params: dict) -> str:
            tool = registry.get(name)
            if not tool:
                return f"Unknown tool: {name}"
            state = {"user_id": str(user_id)}
            return await tool.execute(params, state=state)

        # Both Claude and Gemini implement agentic_stream with the same interface
        if not hasattr(llm, 'agentic_stream'):
            return

        async for event in llm.agentic_stream(
            messages=history,
            tools=tools,
            tool_executor=execute_tool,
            model=model,
        ):
            etype = event.get("type")

            if etype == "text":
                collected_content.append(event["content"])
                yield ChatStreamChunk(type="token", content=event["content"])

            elif etype == "tool_use_start":
                yield ChatStreamChunk(
                    type="tool_call",
                    tool=event["tool"],
                    tool_arg=json.dumps(event.get("input", {})),
                )

            elif etype == "tool_result":
                yield ChatStreamChunk(
                    type="tool_result",
                    tool=event["tool"],
                    content=event.get("result", ""),
                )

            elif etype == "error":
                yield ChatStreamChunk(type="error", error=event["error"])

            elif etype == "done":
                pass  # handled by caller

    # =====================================================================
    # Internals
    # =====================================================================

    @staticmethod
    def extract_tool_calls(text: str, current_provider: str | None = None) -> list[dict]:
        """Extract and validate tool calls from LLM response text.

        Returns a list of dicts: [{"tool": "SWITCH_MODEL", "arg": "claude", "valid": True}, ...]
        """
        results = []
        for match in _TOOL_PATTERN.finditer(text):
            tool_name = match.group(1).upper()
            arg = match.group(2).lower()

            if tool_name == "SWITCH_MODEL":
                all_providers = _UPLINK_PROVIDERS | _LOCAL_PROVIDERS
                if arg not in all_providers:
                    results.append({"tool": tool_name, "arg": arg, "valid": False, "reason": f"Unknown provider: {arg}"})
                    continue
                # Privacy: block Stark → Uplink
                if current_provider in _LOCAL_PROVIDERS and arg in _UPLINK_PROVIDERS:
                    results.append({"tool": tool_name, "arg": arg, "valid": False, "reason": "Privacy policy: cannot switch from local to uplink"})
                    continue
                results.append({"tool": tool_name, "arg": arg, "valid": True})

            elif tool_name == "TOGGLE_VOICE":
                if arg not in ("on", "off"):
                    results.append({"tool": tool_name, "arg": arg, "valid": False, "reason": "Invalid: use 'on' or 'off'"})
                    continue
                results.append({"tool": tool_name, "arg": arg, "valid": True})

        return results

    @staticmethod
    def strip_tool_tags(text: str) -> str:
        """Remove tool call tags from the displayed text."""
        return _TOOL_PATTERN.sub("", text).strip()

    def _resolve_llm_client(self, request: ChatRequest) -> BaseLLMClient:
        """Return the appropriate LLM client based on the request's provider.

        Raises a clear error if the requested provider is unavailable rather
        than silently falling back (which can be confusing).
        """
        provider = request.model_provider
        if provider:
            logger.info("Resolving LLM client for provider: %s", provider)
            return get_llm_client(provider)
        logger.info("Using default LLM client: %s", self.llm_client.provider.value)
        return self.llm_client

    async def _resolve_conversation(
        self,
        user_id: uuid.UUID,
        request: ChatRequest,
    ) -> Conversation:
        """Get an existing conversation or create a new one."""
        if request.conversation_id:
            return await self.get_conversation(request.conversation_id, user_id)

        # Use provider's default model
        llm = self._resolve_llm_client(request)
        create_data = ConversationCreate(
            model=request.model or llm.get_default_model(),
            system_prompt=request.system_prompt,
        )
        return await self.create_conversation(user_id, create_data)

    async def _build_message_history(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        system_prompt: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> list[dict[str, str]]:
        """
        Build the message list to send to the LLM.  Includes an optional
        system prompt followed by the most recent *limit* messages.
        Decrypts stored messages before including them in history.
        Uses per-user system prompts for secondary users.
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        history: list[dict[str, str]] = []

        # Determine the right system prompt based on user
        combined_prompt = await self._get_user_system_prompt(user_id)
        if system_prompt:
            combined_prompt += f"\n\nAdditional instructions:\n{system_prompt}"
        history.append({"role": "system", "content": combined_prompt})

        for msg in messages:
            content = decrypt_message(msg.content, user_id) if user_id else msg.content
            history.append({"role": msg.role, "content": content})

        return history

    async def _get_user_system_prompt(self, user_id: Optional[uuid.UUID]) -> str:
        """Return the appropriate system prompt based on the user.

        The first registered user (owner / Mr. Stark) gets the full JARVIS prompt.
        Secondary users get a limited prompt with their name.
        """
        if not user_id:
            return _JARVIS_SYSTEM_PROMPT

        try:
            from app.models.user import User

            result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return _JARVIS_SYSTEM_PROMPT

            # Check if this is the owner (first/superuser) or has is_superuser flag
            if user.is_superuser:
                return _JARVIS_SYSTEM_PROMPT

            # Check by registration order — owner is the first created user
            first_user = await self.db.execute(
                select(User).order_by(User.created_at.asc()).limit(1)
            )
            owner = first_user.scalar_one_or_none()
            if owner and owner.id == user_id:
                return _JARVIS_SYSTEM_PROMPT

            # Secondary user — use limited prompt
            prefs = user.preferences or {}
            full_name = user.full_name or user.username
            user_context = prefs.get(
                "user_context",
                "A trusted friend of Mr. Stark with access to JARVIS"
            )
            return _JARVIS_SECONDARY_USER_PROMPT.format(
                full_name=full_name,
                user_context=user_context,
            )
        except Exception:
            logger.warning("Failed to load user-specific prompt, using default", exc_info=True)
            return _JARVIS_SYSTEM_PROMPT

    async def _generate_title(
        self,
        first_message: str,
        llm: Optional[BaseLLMClient] = None,
    ) -> str:
        """
        Ask the LLM to produce a concise conversation title (max ~6 words)
        derived from the first user message.  Uses the cheapest available
        model for the given provider.
        """
        try:
            client = llm or self.llm_client
            prompt_messages = [
                {
                    "role": "system",
                    "content": (
                        "Generate a very short title (maximum 6 words) for a "
                        "conversation that starts with the following message. "
                        "Return ONLY the title text, no quotes, no punctuation "
                        "at the end."
                    ),
                },
                {"role": "user", "content": first_message},
            ]
            response = await client.chat_completion(
                messages=prompt_messages,
                model=client.get_cheap_model(),
                temperature=0.5,
                max_tokens=20,
            )
            title = response["content"].strip().strip('"').strip("'")
            return title[:255]
        except Exception:
            logger.warning("Title generation failed; falling back to truncation")
            return first_message[:80].strip()

    # ── Redis cache helpers ──────────────────────────────────────────────

    async def _cache_conversation(self, conversation: Conversation) -> None:
        """Store conversation metadata in Redis."""
        try:
            key = _CONV_CACHE_KEY.format(conv_id=conversation.id)
            payload = json.dumps({
                "id": str(conversation.id),
                "user_id": str(conversation.user_id),
                "title": conversation.title,
                "model": conversation.model,
                "is_archived": conversation.is_archived,
                "message_count": conversation.message_count,
            })
            await self.redis.cache_set(key, payload, ttl=_CONV_CACHE_TTL)
        except Exception:
            logger.debug("Redis cache write failed (non-critical)", exc_info=True)

    async def _get_cached_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> Optional[dict]:
        """Retrieve cached conversation metadata, if available."""
        try:
            key = _CONV_CACHE_KEY.format(conv_id=conversation_id)
            raw = await self.redis.cache_get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            logger.debug("Redis cache read failed (non-critical)", exc_info=True)
        return None

    async def _invalidate_conversation_cache(
        self,
        conversation_id: uuid.UUID,
    ) -> None:
        """Remove a conversation from the cache."""
        try:
            key = _CONV_CACHE_KEY.format(conv_id=conversation_id)
            await self.redis.cache_delete(key)
        except Exception:
            logger.debug("Redis cache invalidation failed (non-critical)", exc_info=True)
