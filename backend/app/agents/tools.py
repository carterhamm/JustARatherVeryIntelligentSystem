"""
Unified tool registry for the J.A.R.V.I.S. agent system.

Every tool is a class with:
  - ``name``  (str)
  - ``description`` (str)
  - ``async execute(params, state=None) -> str``

The ``get_tool_registry()`` factory returns a name->tool mapping that
the executor node iterates over.
"""

from __future__ import annotations

import json
import logging
import math
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.state import AgentState

logger = logging.getLogger("jarvis.agents.tools")


async def _get_google_tokens(state: Optional[AgentState]) -> Optional[dict]:
    """Load per-user Google OAuth tokens from DB preferences.

    Returns the token dict if connected, or None if not.
    """
    user_id = (state or {}).get("user_id", "")
    if not user_id:
        return None
    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as _AS
        from sqlalchemy.orm import sessionmaker
        from app.config import settings
        from app.models.user import User

        engine = create_async_engine(settings.DATABASE_URL)
        async_session = sessionmaker(engine, class_=_AS, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            if user and user.preferences and user.preferences.get("google_tokens"):
                return user.preferences["google_tokens"]
        await engine.dispose()
    except Exception:
        logger.debug("Failed to load Google tokens for user %s", user_id, exc_info=True)
    return None


# ═════════════════════════════════════════════════════════════════════════
# Base class
# ═════════════════════════════════════════════════════════════════════════

class BaseTool(ABC):
    """Abstract base for all JARVIS tools."""

    name: str = ""
    description: str = ""

    async def run(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        """Execute with deep logging — wraps execute()."""
        user_id = (state or {}).get("user_id", "?")
        logger.info(
            "TOOL_START tool=%s user=%s params=%s",
            self.name, user_id, json.dumps(params, default=str)[:500],
        )
        t0 = time.monotonic()
        try:
            result = await self.execute(params, state=state)
            elapsed = time.monotonic() - t0
            # Truncate result for logging
            preview = result[:300].replace("\n", " ") if result else "(empty)"
            logger.info(
                "TOOL_OK tool=%s user=%s elapsed=%.2fs result_len=%d preview=%s",
                self.name, user_id, elapsed, len(result), preview,
            )
            return result
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.error(
                "TOOL_ERROR tool=%s user=%s elapsed=%.2fs error=%s",
                self.name, user_id, elapsed, exc, exc_info=True,
            )
            return f"Tool '{self.name}' failed: {exc}"

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        """Execute the tool and return a human-readable result string."""
        ...


# ═════════════════════════════════════════════════════════════════════════
# Knowledge tools
# ═════════════════════════════════════════════════════════════════════════

class SearchKnowledgeTool(BaseTool):
    """Search the J.A.R.V.I.S. private knowledge base."""

    name = "search_knowledge"
    description = (
        "Search the user's personal knowledge base (documents, notes, "
        "emails, messages) for information about Mr. Stark, his family, "
        "preferences, contacts, and personal details.  Params: query (str), "
        "limit? (int, default 5)."
    )

    # Cache loaded knowledge files in memory
    _knowledge_cache: Optional[list[dict[str, str]]] = None

    @classmethod
    def _load_knowledge_files(cls) -> list[dict[str, str]]:
        """Load local knowledge files from backend/knowledge/ directory."""
        if cls._knowledge_cache is not None:
            return cls._knowledge_cache

        import pathlib

        knowledge_dir = pathlib.Path(__file__).parent.parent.parent / "knowledge"
        entries: list[dict[str, str]] = []

        if knowledge_dir.exists():
            for fpath in knowledge_dir.glob("*.md"):
                try:
                    content = fpath.read_text(encoding="utf-8")
                    # Split into sections by ## headers for granular search
                    sections = content.split("\n## ")
                    title = fpath.stem.replace("-", " ").title()
                    for i, section in enumerate(sections):
                        section = section.strip()
                        if not section:
                            continue
                        # First section includes the # header
                        if i == 0 and section.startswith("# "):
                            header_end = section.find("\n")
                            header = section[:header_end].lstrip("# ").strip() if header_end > 0 else title
                            body = section[header_end:].strip() if header_end > 0 else section
                        else:
                            header_end = section.find("\n")
                            header = section[:header_end].strip() if header_end > 0 else section
                            body = section[header_end:].strip() if header_end > 0 else ""
                        entries.append({
                            "title": f"{title} — {header}",
                            "text": f"{header}\n{body}" if body else header,
                            "source": fpath.name,
                        })
                except Exception as exc:
                    logger.warning("Failed to load knowledge file %s: %s", fpath, exc)

        cls._knowledge_cache = entries
        logger.info("Loaded %d knowledge sections from local files", len(entries))
        return entries

    def _search_local(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Simple keyword search through local knowledge files."""
        entries = self._load_knowledge_files()
        if not entries:
            return []

        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 2]

        scored: list[tuple[float, dict]] = []
        for entry in entries:
            text_lower = entry["text"].lower()
            title_lower = entry["title"].lower()

            # Score based on keyword matches
            score = 0.0
            for word in query_words:
                if word in text_lower:
                    score += 1.0
                if word in title_lower:
                    score += 1.5  # title matches weighted higher

            # Exact phrase match bonus
            if query_lower in text_lower:
                score += 3.0

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"score": s, "payload": {"title": e["title"], "text": e["text"]}}
            for s, e in scored[:limit]
        ]

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        query = params.get("query", "")
        limit = params.get("limit", 5)
        if not query:
            return "No search query provided."

        results: list[dict] = []

        # Try Qdrant vector search first (if configured)
        try:
            from app.db.qdrant import get_qdrant_store
            from app.graphrag.vector_store import VectorStore

            store = get_qdrant_store()
            vs = VectorStore(qdrant_store=store)
            # No user_id filter — JARVIS needs all knowledge (system + user)
            # Per-user isolation is handled by separate system prompts
            qdrant_results = await vs.search_similar(
                query=query,
                limit=limit,
                min_score=0.5,
            )
            if qdrant_results:
                results = qdrant_results
        except Exception:
            logger.debug("Qdrant search unavailable, using local knowledge files")

        # Fall back to local knowledge file search
        if not results:
            results = self._search_local(query, limit)

        if not results:
            return f"No relevant results found for: '{query}'"

        lines: list[str] = []
        for i, hit in enumerate(results, 1):
            payload = hit.get("payload", {})
            score = hit.get("score", 0.0)
            title = payload.get("title", "Untitled")
            text = payload.get("text", payload.get("content", ""))[:500]
            lines.append(f"{i}. [{score:.2f}] {title}: {text}")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Email tools
# ═════════════════════════════════════════════════════════════════════════

class SendEmailTool(BaseTool):
    """Compose and send an email via Gmail."""

    name = "send_email"
    description = (
        "Send an email using the user's Gmail account.  "
        "Params: to (str), subject (str), body (str), "
        "cc? (str), bcc? (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        tokens = await _get_google_tokens(state)
        if not tokens:
            return (
                "Gmail is not connected. The user needs to sign in with Google first.\n"
                "They can do this at: https://app.malibupoint.dev/connect/google"
            )

        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")

        if not to or not subject:
            return "Missing required email fields (to, subject)."

        try:
            from app.integrations.google_workspace import gmail_send
            result = await gmail_send(tokens, to=to, subject=subject, body=body)
            return (
                f"Email sent successfully.\n"
                f"  To: {to}\n"
                f"  Subject: {subject}\n"
                f"  Message ID: {result.get('id', 'N/A')}"
            )
        except Exception as exc:
            return f"Failed to send email: {exc}"


class ReadEmailTool(BaseTool):
    """Read recent emails from the user's Gmail inbox."""

    name = "read_email"
    description = (
        "Read recent emails from the user's Gmail inbox.  "
        "Params: query? (str, Gmail search query), limit? (int, default 5)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        tokens = await _get_google_tokens(state)
        if not tokens:
            return (
                "Gmail is not connected. The user needs to sign in with Google first.\n"
                "They can do this at: https://app.malibupoint.dev/connect/google"
            )

        query = params.get("query", "")
        limit = params.get("limit", 5)

        try:
            from app.integrations.google_workspace import gmail_read
            emails = await gmail_read(tokens, query=query, limit=limit)
        except Exception as exc:
            return f"Failed to read emails: {exc}"

        if not emails:
            return "No emails found matching the query."

        lines: list[str] = []
        for i, email in enumerate(emails, 1):
            lines.append(
                f"{i}. From: {email.get('from', 'Unknown')}\n"
                f"   Subject: {email.get('subject', '(no subject)')}\n"
                f"   Date: {email.get('date', 'Unknown')}\n"
                f"   Snippet: {email.get('snippet', '')[:150]}"
            )
        return "\n".join(lines)


class SendJarvisEmailTool(BaseTool):
    """Send an email from JARVIS's own address (jarvis@malibupoint.dev) via Resend."""

    name = "send_jarvis_email"
    description = (
        "Send an email FROM jarvis@malibupoint.dev (JARVIS's own email address). "
        "Use this for JARVIS-initiated emails like daily briefings, alerts, and reports "
        "sent TO the owner. NEVER use this to impersonate the owner. "
        "Params: to (str), subject (str), body (str), html? (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.resend_email import send_email

        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")
        html = params.get("html")

        if not to or not subject:
            return "Missing required fields (to, subject)."

        result = await send_email(to=to, subject=subject, body=body, html=html)

        if result.get("error"):
            return f"Failed to send email: {result['error']}"

        return (
            f"JARVIS email sent successfully.\n"
            f"  From: jarvis@malibupoint.dev\n"
            f"  To: {result.get('to', to)}\n"
            f"  Subject: {result.get('subject', subject)}\n"
            f"  Email ID: {result.get('email_id', 'N/A')}"
        )


# ═════════════════════════════════════════════════════════════════════════
# Calendar tools
# ═════════════════════════════════════════════════════════════════════════

class CreateCalendarEventTool(BaseTool):
    """Create a new calendar event."""

    name = "create_calendar_event"
    description = (
        "Create a calendar event on Google Calendar.  "
        "Params: title (str), start (ISO datetime), end (ISO datetime), "
        "description? (str), location? (str), attendees? (list[str])."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        tokens = await _get_google_tokens(state)
        if not tokens:
            return (
                "Google Calendar is not connected. The user needs to sign in with Google first.\n"
                "They can do this at: https://app.malibupoint.dev/connect/google"
            )

        title = params.get("title", "")
        start = params.get("start", "")
        end = params.get("end", "")
        description = params.get("description", "")
        location = params.get("location", "")
        attendees = params.get("attendees")

        if not title or not start or not end:
            return "Missing required fields (title, start, end)."

        try:
            from app.integrations.google_workspace import calendar_create_event
            result = await calendar_create_event(
                tokens, title=title, start=start, end=end,
                description=description, location=location, attendees=attendees,
            )
            return (
                f"Calendar event created.\n"
                f"  Title: {result.get('title', title)}\n"
                f"  Start: {result.get('start', start)}\n"
                f"  End: {result.get('end', end)}\n"
                f"  Link: {result.get('link', 'N/A')}"
            )
        except Exception as exc:
            return f"Failed to create calendar event: {exc}"


class ListCalendarEventsTool(BaseTool):
    """List upcoming calendar events."""

    name = "list_calendar_events"
    description = (
        "List upcoming calendar events within a date range.  "
        "Params: start_date (ISO date), end_date (ISO date)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        tokens = await _get_google_tokens(state)
        if not tokens:
            return (
                "Google Calendar is not connected. The user needs to sign in with Google first.\n"
                "They can do this at: https://app.malibupoint.dev/connect/google"
            )

        start_date = params.get("start_date", "")
        end_date = params.get("end_date", "")
        if not start_date or not end_date:
            return "Missing required fields (start_date, end_date)."

        try:
            from app.integrations.google_workspace import calendar_list_events
            events = await calendar_list_events(tokens, start_date=start_date, end_date=end_date)
        except Exception as exc:
            return f"Failed to list calendar events: {exc}"

        if not events:
            return f"No events found between {start_date} and {end_date}."

        lines: list[str] = []
        for i, ev in enumerate(events, 1):
            lines.append(
                f"{i}. {ev.get('title', 'Untitled')}\n"
                f"   {ev.get('start', '?')} - {ev.get('end', '?')}\n"
                f"   {ev.get('description', '')}"
            )
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Reminder tool
# ═════════════════════════════════════════════════════════════════════════

class SetReminderTool(BaseTool):
    """Set a reminder for the user, persisted to the database."""

    name = "set_reminder"
    description = (
        "Set a reminder that will notify the user at the specified time.  "
        "Params: message (str), remind_at (ISO datetime)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.db.session import transaction
        from app.models.reminder import Reminder

        message = params.get("message", "")
        remind_at = params.get("remind_at", "")

        if not message or not remind_at:
            return "Missing required fields (message, remind_at)."

        # Parse the remind_at datetime
        try:
            if remind_at.endswith("Z"):
                remind_dt = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
            else:
                remind_dt = datetime.fromisoformat(remind_at)
            # If no timezone, assume UTC
            if remind_dt.tzinfo is None:
                remind_dt = remind_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            return f"Invalid remind_at datetime format: {remind_at} ({exc})"

        # Extract user_id and conversation_id from agent state
        user_id_str = (state or {}).get("user_id", "")
        conversation_id_str = (state or {}).get("conversation_id", "")

        user_id = None
        conversation_id = None
        if user_id_str:
            import uuid as uuid_mod
            try:
                user_id = uuid_mod.UUID(user_id_str)
            except ValueError:
                pass
        if conversation_id_str:
            import uuid as uuid_mod
            try:
                conversation_id = uuid_mod.UUID(conversation_id_str)
            except ValueError:
                pass

        # Persist the reminder to the database
        async with transaction() as session:
            reminder = Reminder(
                user_id=user_id,
                message=message,
                remind_at=remind_dt,
                conversation_id=conversation_id,
            )
            session.add(reminder)

        logger.info(
            "Reminder persisted: id=%s message=%r remind_at=%s user_id=%s",
            reminder.id,
            message,
            remind_at,
            user_id,
        )

        return (
            f"Reminder set successfully.\n"
            f"  Message: {message}\n"
            f"  Remind at: {remind_at}\n"
            f"  Reminder ID: {reminder.id}\n"
            f"  Status: scheduled (persisted to database)"
        )


# ═════════════════════════════════════════════════════════════════════════
# Smart home tool
# ═════════════════════════════════════════════════════════════════════════

class SmartHomeControlTool(BaseTool):
    """Control a smart home device via the Matter protocol bridge."""

    name = "smart_home_control"
    description = (
        "Control a smart-home device (lights, thermostat, locks, etc.).  "
        "Params: device_id (str), command (str: on/off/set_brightness/"
        "set_temperature/lock/unlock/set_color), params? (dict)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.matter import MatterClient

        device_id = params.get("device_id", "")
        command = params.get("command", "")
        cmd_params = params.get("params", {})

        if not device_id or not command:
            return "Missing required fields (device_id, command)."

        async with MatterClient() as matter:
            success = await matter.control_device(
                device_id=device_id, command=command, params=cmd_params,
            )

        if success:
            return (
                f"Device '{device_id}' command '{command}' executed successfully."
            )
        return f"Failed to execute '{command}' on device '{device_id}'."


# ═════════════════════════════════════════════════════════════════════════
# Web search tool
# ═════════════════════════════════════════════════════════════════════════

class WebSearchTool(BaseTool):
    """Search the web for current information."""

    name = "web_search"
    description = (
        "Search the web for up-to-date information, facts, celebrity info, "
        "sports scores, current events, or anything you're unsure about.  "
        "Params: query (str), max_results? (int, default 5)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        query = params.get("query", "")
        max_results = params.get("max_results", 5)
        if not query:
            return "No search query provided."

        # Try dedicated search APIs first (Tavily, SerpAPI, Brave)
        try:
            from app.integrations.web_search import WebSearchClient

            async with WebSearchClient() as client:
                results = await client.search(query=query, max_results=max_results)

            if results and not any(r.get("title") == "Search unavailable" for r in results):
                lines: list[str] = [f"Web search results for: '{query}'\n"]
                for i, result in enumerate(results, 1):
                    title = result.get("title", "Untitled")
                    url = result.get("url", "")
                    snippet = result.get("snippet", "")[:300]
                    lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")
                return "\n".join(lines)
        except Exception as exc:
            logger.debug("Dedicated search APIs failed: %s", exc)

        # Fallback: use Gemini with Google Search grounding
        try:
            return await self._gemini_grounded_search(query)
        except Exception as exc:
            logger.warning("Gemini grounded search also failed: %s", exc)

        return f"Web search is currently unavailable. Please answer '{query}' from your training knowledge if possible."

    async def _gemini_grounded_search(self, query: str) -> str:
        """Use Gemini API with Google Search grounding as a free fallback."""
        from app.config import settings

        if not settings.GOOGLE_GEMINI_API_KEY:
            raise RuntimeError("Gemini API key not configured")

        import httpx

        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent"
        payload = {
            "contents": [{"parts": [{"text": f"Search the web and answer: {query}"}]}],
            "tools": [{"google_search": {}}],
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                json=payload,
                params={"key": settings.GOOGLE_GEMINI_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract text from Gemini response
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [p.get("text", "") for p in parts if p.get("text")]
            if texts:
                return f"Web search results for '{query}':\n\n" + "\n".join(texts)

        return f"No results found for: '{query}'"


# ═════════════════════════════════════════════════════════════════════════
# Weather tool
# ═════════════════════════════════════════════════════════════════════════

class WeatherTool(BaseTool):
    """Get current weather or a forecast for a location."""

    name = "weather"
    description = (
        "Get current weather conditions or a multi-day forecast for a "
        "location.  Params: action (str: 'current' | 'forecast'), "
        "city? (str), lat? (float), lon? (float), days? (int, default 5), "
        "units? (str: 'metric' | 'imperial', default 'metric')."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.weather import WeatherClient

        action = params.get("action", "current")
        city = params.get("city")
        lat = params.get("lat")
        lon = params.get("lon")
        units = params.get("units", "metric")

        if not city and (lat is None or lon is None):
            return "Missing required location: provide 'city' or both 'lat' and 'lon'."

        async with WeatherClient() as client:
            if action == "forecast":
                days = params.get("days", 5)
                result = await client.get_forecast(
                    city=city, lat=lat, lon=lon, days=days, units=units,
                )

                if "error" in result:
                    return result["error"]

                unit = result.get("units", "C")
                lines: list[str] = [
                    f"Weather forecast for {result.get('location', 'Unknown')}, "
                    f"{result.get('country', '')}:\n"
                ]
                for day in result.get("forecast", []):
                    lines.append(
                        f"  {day['date']}: {day.get('description', '')}, "
                        f"{day.get('temp_min')}–{day.get('temp_max')}°{unit}, "
                        f"humidity {day.get('humidity_avg')}%, "
                        f"wind {day.get('wind_speed_avg')} m/s"
                    )
                return "\n".join(lines)

            else:  # current
                result = await client.get_current(
                    city=city, lat=lat, lon=lon, units=units,
                )

                if "error" in result:
                    return result["error"]

                unit = result.get("units", "C")
                return (
                    f"Current weather in {result.get('location', 'Unknown')}, "
                    f"{result.get('country', '')}:\n"
                    f"  Conditions: {result.get('description', '')}\n"
                    f"  Temperature: {result.get('temperature')}°{unit} "
                    f"(feels like {result.get('feels_like')}°{unit})\n"
                    f"  Range: {result.get('temp_min')}–{result.get('temp_max')}°{unit}\n"
                    f"  Humidity: {result.get('humidity')}%\n"
                    f"  Wind: {result.get('wind_speed')} m/s, {result.get('wind_direction')}°\n"
                    f"  Pressure: {result.get('pressure')} hPa\n"
                    f"  Visibility: {result.get('visibility')} m\n"
                    f"  Clouds: {result.get('clouds')}%"
                )


# ═════════════════════════════════════════════════════════════════════════
# News tool
# ═════════════════════════════════════════════════════════════════════════

class NewsTool(BaseTool):
    """Get top news headlines or search for news articles."""

    name = "news"
    description = (
        "Get top news headlines or search for news articles.  "
        "Params: action (str: 'headlines' | 'search'), "
        "query? (str, required for search), "
        "country? (str, default 'us'), "
        "category? (str: business/entertainment/general/health/science/"
        "sports/technology), sort_by? (str, default 'relevancy'), "
        "limit? (int, default 10)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.news import NewsClient

        action = params.get("action", "headlines")
        limit = params.get("limit", 10)

        async with NewsClient() as client:
            if action == "search":
                query = params.get("query", "")
                if not query:
                    return "Missing required 'query' parameter for news search."
                sort_by = params.get("sort_by", "relevancy")
                articles = await client.search(
                    query=query, sort_by=sort_by, page_size=limit,
                )
            else:  # headlines
                country = params.get("country", "us")
                category = params.get("category")
                articles = await client.get_headlines(
                    country=country, category=category, page_size=limit,
                )

        if not articles:
            return "No news articles found."

        lines: list[str] = []
        for i, article in enumerate(articles, 1):
            lines.append(
                f"{i}. {article.get('title', 'Untitled')}\n"
                f"   Source: {article.get('source', 'Unknown')} | "
                f"{article.get('publishedAt', '')}\n"
                f"   {article.get('description', '')[:200]}\n"
                f"   URL: {article.get('url', '')}"
            )
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Spotify tool
# ═════════════════════════════════════════════════════════════════════════

class SpotifyTool(BaseTool):
    """Control Spotify playback and search for music."""

    name = "spotify"
    description = (
        "Interact with Spotify: check what's playing, search tracks, or "
        "get recommendations.  Params: action (str: 'now_playing' | "
        "'search' | 'recommendations'), query? (str, for search), "
        "seed_tracks? (list[str]), seed_artists? (list[str]), "
        "seed_genres? (list[str]), limit? (int, default 10)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.spotify import SpotifyClient

        action = params.get("action", "now_playing")
        limit = params.get("limit", 10)

        async with SpotifyClient() as client:
            if action == "now_playing":
                result = await client.get_currently_playing()
                if not result.get("is_playing"):
                    return result.get("message", "Nothing is currently playing.")
                return (
                    f"Now playing on Spotify:\n"
                    f"  Track: {result.get('track', 'Unknown')}\n"
                    f"  Artist: {result.get('artist', 'Unknown')}\n"
                    f"  Album: {result.get('album', '')}\n"
                    f"  Progress: {self._format_ms(result.get('progress_ms', 0))} / "
                    f"{self._format_ms(result.get('duration_ms', 0))}\n"
                    f"  URL: {result.get('url', '')}"
                )

            elif action == "search":
                query = params.get("query", "")
                if not query:
                    return "Missing required 'query' parameter for Spotify search."
                tracks = await client.search_tracks(query=query, limit=limit)
                if not tracks:
                    return f"No tracks found for: '{query}'"

                lines: list[str] = [f"Spotify search results for: '{query}'\n"]
                for i, track in enumerate(tracks, 1):
                    lines.append(
                        f"{i}. {track.get('name', 'Unknown')} - "
                        f"{track.get('artist', 'Unknown')}\n"
                        f"   Album: {track.get('album', '')}\n"
                        f"   Duration: {self._format_ms(track.get('duration_ms', 0))}\n"
                        f"   URL: {track.get('url', '')}"
                    )
                return "\n".join(lines)

            elif action == "recommendations":
                seed_tracks = params.get("seed_tracks")
                seed_artists = params.get("seed_artists")
                seed_genres = params.get("seed_genres")

                if not seed_tracks and not seed_artists and not seed_genres:
                    return (
                        "Provide at least one seed: 'seed_tracks', "
                        "'seed_artists', or 'seed_genres'."
                    )

                tracks = await client.get_recommendations(
                    seed_tracks=seed_tracks,
                    seed_artists=seed_artists,
                    seed_genres=seed_genres,
                    limit=limit,
                )
                if not tracks:
                    return "No recommendations found for the given seeds."

                lines = ["Spotify recommendations:\n"]
                for i, track in enumerate(tracks, 1):
                    lines.append(
                        f"{i}. {track.get('name', 'Unknown')} - "
                        f"{track.get('artist', 'Unknown')}\n"
                        f"   Album: {track.get('album', '')}\n"
                        f"   URL: {track.get('url', '')}"
                    )
                return "\n".join(lines)

            else:
                return (
                    f"Unknown Spotify action: '{action}'.  "
                    f"Use 'now_playing', 'search', or 'recommendations'."
                )

    @staticmethod
    def _format_ms(ms: int) -> str:
        """Convert milliseconds to MM:SS format."""
        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"


# ═════════════════════════════════════════════════════════════════════════
# iMCP tools — native macOS access (Calendar, Contacts, Messages,
#               Reminders, Location, Maps, Weather) via MCP protocol
# ═════════════════════════════════════════════════════════════════════════

class _IMCPBaseTool(BaseTool):
    """Base class for tools backed by the iMCP server."""

    _mcp_tool_name: str = ""

    async def _call_imcp(self, arguments: dict[str, Any]) -> str:
        from app.integrations.mcp_client import get_imcp_client

        client = get_imcp_client()
        try:
            await client.start()
            result = await client.call_tool(self._mcp_tool_name, arguments)
            if isinstance(result, str):
                return result
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.exception("iMCP tool '%s' failed: %s", self._mcp_tool_name, exc)
            return f"Error calling {self._mcp_tool_name}: {exc}"


class IMCPCalendarListTool(_IMCPBaseTool):
    name = "mac_calendars_list"
    description = "List all available calendars on this Mac. No params."
    _mcp_tool_name = "calendars_list"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        return await self._call_imcp({})


class IMCPEventsFetchTool(_IMCPBaseTool):
    name = "mac_events_fetch"
    description = (
        "Fetch calendar events from this Mac with filters.  "
        "Params: start? (ISO datetime), end? (ISO datetime), "
        "calendars? (list[str]), query? (str), includeAllDay? (bool)."
    )
    _mcp_tool_name = "events_fetch"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        args: dict[str, Any] = {}
        for key in ("start", "end", "query", "includeAllDay", "calendars", "status", "availability", "hasAlarms", "isRecurring"):
            if key in params:
                args[key] = params[key]
        return await self._call_imcp(args)


class IMCPEventsCreateTool(_IMCPBaseTool):
    name = "mac_events_create"
    description = (
        "Create a calendar event on this Mac.  "
        "Params: title (str, required), start (ISO datetime, required), "
        "end (ISO datetime, required), calendar? (str), location? (str), "
        "notes? (str), url? (str), isAllDay? (bool), alarms? (list)."
    )
    _mcp_tool_name = "events_create"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if not params.get("title") or not params.get("start") or not params.get("end"):
            return "Missing required fields: title, start, end."
        return await self._call_imcp(params)


class IMCPContactsMeTool(_IMCPBaseTool):
    name = "mac_contacts_me"
    description = "Get the user's own contact information from this Mac. No params."
    _mcp_tool_name = "contacts_me"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        return await self._call_imcp({})


class IMCPContactsSearchTool(_IMCPBaseTool):
    name = "mac_contacts_search"
    description = (
        "Search contacts on this Mac by name, phone, or email.  "
        "Params: name? (str), phone? (str), email? (str). At least one required."
    )
    _mcp_tool_name = "contacts_search"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        args = {k: v for k, v in params.items() if k in ("name", "phone", "email") and v}
        if not args:
            return "Provide at least one of: name, phone, email."
        return await self._call_imcp(args)


class IMCPContactsCreateTool(_IMCPBaseTool):
    name = "mac_contacts_create"
    description = (
        "Create a new contact on this Mac.  "
        "Params: givenName (str, required), familyName? (str), "
        "organizationName? (str), jobTitle? (str), phoneNumbers? (list), "
        "emailAddresses? (list), birthday? (dict)."
    )
    _mcp_tool_name = "contacts_create"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if not params.get("givenName"):
            return "Missing required field: givenName."
        return await self._call_imcp(params)


class IMCPMessagesFetchTool(_IMCPBaseTool):
    name = "mac_messages_fetch"
    description = (
        "Fetch iMessages/SMS from this Mac.  "
        "Params: participants? (list[str], phone/email in E.164), "
        "start? (ISO datetime), end? (ISO datetime), "
        "query? (str), limit? (int, default 30)."
    )
    _mcp_tool_name = "messages_fetch"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        args: dict[str, Any] = {}
        for key in ("participants", "start", "end", "query", "limit"):
            if key in params:
                args[key] = params[key]
        return await self._call_imcp(args)


class IMCPRemindersListsTool(_IMCPBaseTool):
    name = "mac_reminders_lists"
    description = "List all reminder lists on this Mac. No params."
    _mcp_tool_name = "reminders_lists"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        return await self._call_imcp({})


class IMCPRemindersFetchTool(_IMCPBaseTool):
    name = "mac_reminders_fetch"
    description = (
        "Fetch reminders from this Mac.  "
        "Params: completed? (bool), start? (ISO datetime), "
        "end? (ISO datetime), lists? (list[str]), query? (str)."
    )
    _mcp_tool_name = "reminders_fetch"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        args: dict[str, Any] = {}
        for key in ("completed", "start", "end", "lists", "query"):
            if key in params:
                args[key] = params[key]
        return await self._call_imcp(args)


class IMCPRemindersCreateTool(_IMCPBaseTool):
    name = "mac_reminders_create"
    description = (
        "Create a reminder on this Mac.  "
        "Params: title (str, required), due? (ISO datetime), "
        "list? (str), notes? (str), priority? (str), alarms? (list[int] minutes)."
    )
    _mcp_tool_name = "reminders_create"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if not params.get("title"):
            return "Missing required field: title."
        return await self._call_imcp(params)


class IMCPLocationCurrentTool(_IMCPBaseTool):
    name = "mac_location_current"
    description = "Get the user's current location from this Mac. No params."
    _mcp_tool_name = "location_current"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        return await self._call_imcp({})


class IMCPLocationGeocodeTool(_IMCPBaseTool):
    name = "mac_location_geocode"
    description = (
        "Convert an address to coordinates.  Params: address (str, required)."
    )
    _mcp_tool_name = "location_geocode"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if not params.get("address"):
            return "Missing required field: address."
        return await self._call_imcp({"address": params["address"]})


class IMCPMapsSearchTool(_IMCPBaseTool):
    name = "mac_maps_search"
    description = (
        "Search for places/addresses using Apple Maps.  "
        "Params: query (str, required), region? ({latitude, longitude, radius?})."
    )
    _mcp_tool_name = "maps_search"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if not params.get("query"):
            return "Missing required field: query."
        args: dict[str, Any] = {"query": params["query"]}
        if "region" in params:
            args["region"] = params["region"]
        return await self._call_imcp(args)


class IMCPMapsDirectionsTool(_IMCPBaseTool):
    name = "mac_maps_directions"
    description = (
        "Get directions between locations via Apple Maps.  "
        "Params: originAddress? (str), destinationAddress? (str), "
        "originCoordinates? ({latitude, longitude}), "
        "destinationCoordinates? ({latitude, longitude}), "
        "transportType? (str: automobile/walking/transit/any)."
    )
    _mcp_tool_name = "maps_directions"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        return await self._call_imcp(params)


class IMCPMapsETATool(_IMCPBaseTool):
    name = "mac_maps_eta"
    description = (
        "Get travel time estimate between two points.  "
        "Params: originLatitude (float), originLongitude (float), "
        "destinationLatitude (float), destinationLongitude (float), "
        "transportType? (str: automobile/walking/transit)."
    )
    _mcp_tool_name = "maps_eta"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        required = ("originLatitude", "originLongitude", "destinationLatitude", "destinationLongitude")
        if not all(params.get(k) is not None for k in required):
            return f"Missing required fields: {', '.join(required)}"
        return await self._call_imcp(params)


class IMCPWeatherCurrentTool(_IMCPBaseTool):
    name = "mac_weather_current"
    description = (
        "Get current weather from Apple Weather (no API key needed).  "
        "Params: latitude (float, required), longitude (float, required)."
    )
    _mcp_tool_name = "weather_current"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if params.get("latitude") is None or params.get("longitude") is None:
            return "Missing required fields: latitude, longitude."
        return await self._call_imcp({
            "latitude": params["latitude"],
            "longitude": params["longitude"],
        })


class IMCPWeatherForecastTool(_IMCPBaseTool):
    name = "mac_weather_forecast"
    description = (
        "Get daily weather forecast from Apple Weather.  "
        "Params: latitude (float, required), longitude (float, required), "
        "days? (int, 1-10, default 7)."
    )
    _mcp_tool_name = "weather_daily"

    async def execute(self, params: dict[str, Any], *, state: Optional[AgentState] = None) -> str:
        if params.get("latitude") is None or params.get("longitude") is None:
            return "Missing required fields: latitude, longitude."
        args: dict[str, Any] = {
            "latitude": params["latitude"],
            "longitude": params["longitude"],
        }
        if "days" in params:
            args["days"] = params["days"]
        return await self._call_imcp(args)


# ═════════════════════════════════════════════════════════════════════════
# Calculator tool
# ═════════════════════════════════════════════════════════════════════════

class CalculatorTool(BaseTool):
    """Evaluate mathematical expressions safely."""

    name = "calculator"
    description = (
        "Evaluate a mathematical expression.  Supports basic arithmetic, "
        "exponents, sqrt, log, trig functions.  Params: expression (str)."
    )

    # Allowed names in the evaluation namespace
    _SAFE_NAMES: dict[str, Any] = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "pi": math.pi,
        "e": math.e,
        "ceil": math.ceil,
        "floor": math.floor,
        "factorial": math.factorial,
    }

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        expression = params.get("expression", "")
        if not expression:
            return "No expression provided."

        try:
            # Restrict builtins to prevent arbitrary code execution
            result = eval(expression, {"__builtins__": {}}, self._SAFE_NAMES)  # noqa: S307
            return f"{expression} = {result}"
        except ZeroDivisionError:
            return f"Error: Division by zero in expression '{expression}'."
        except Exception as exc:
            return f"Error evaluating '{expression}': {exc}"


# ═════════════════════════════════════════════════════════════════════════
# DateTime tool
# ═════════════════════════════════════════════════════════════════════════

class DateTimeTool(BaseTool):
    """Get current date/time and perform timezone operations."""

    name = "date_time"
    description = (
        "Get the current date and time, or convert between timezones.  "
        "Params: timezone? (str, e.g. 'US/Eastern'), "
        "operation? (str: 'now' | 'convert', default 'now')."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        import zoneinfo

        operation = params.get("operation", "now")
        tz_name = params.get("timezone", "America/Denver")

        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            return f"Unknown timezone: '{tz_name}'.  Use IANA names (e.g. 'US/Eastern', 'Europe/London')."

        now = datetime.now(tz=tz)
        # Round up ~1 minute to account for LLM processing + TTS delivery latency
        from datetime import timedelta
        display_time = now + timedelta(seconds=45)

        if operation == "now":
            return (
                f"Current date/time ({tz_name}):\n"
                f"  Date:  {display_time.strftime('%A, %B %d, %Y')}\n"
                f"  Time:  {display_time.strftime('%I:%M %p %Z')}\n"
                f"  Note:  Tell the user this time. Do NOT say seconds, just hour and minutes."
            )
        elif operation == "convert":
            source_tz_name = params.get("source_timezone", "UTC")
            source_time_str = params.get("source_time", "")
            if not source_time_str:
                return "Missing 'source_time' for conversion."
            try:
                source_tz = zoneinfo.ZoneInfo(source_tz_name)
                source_dt = datetime.fromisoformat(source_time_str).replace(tzinfo=source_tz)
                converted = source_dt.astimezone(tz)
                return (
                    f"Converted time:\n"
                    f"  From: {source_dt.isoformat()} ({source_tz_name})\n"
                    f"  To:   {converted.isoformat()} ({tz_name})"
                )
            except Exception as exc:
                return f"Conversion error: {exc}"
        else:
            return f"Unknown operation: '{operation}'.  Use 'now' or 'convert'."


# ═════════════════════════════════════════════════════════════════════════
# Google Drive tool
# ═════════════════════════════════════════════════════════════════════════

class GoogleDriveTool(BaseTool):
    """Search, list, and read Google Drive files."""

    name = "google_drive"
    description = (
        "Interact with Google Drive: list, search, read files.  "
        "Params: action (str: 'list' | 'search' | 'read'), "
        "query? (str), file_id? (str), folder_id? (str), limit? (int)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        tokens = await _get_google_tokens(state)
        if not tokens:
            return (
                "Google Drive is not connected. The user needs to sign in with Google first.\n"
                "They can do this at: https://app.malibupoint.dev/connect/google"
            )

        action = params.get("action", "list")

        try:
            from app.integrations.google_workspace import drive_list_files

            if action in ("list", "search"):
                query = params.get("query", "")
                folder_id = params.get("folder_id", "")
                limit = params.get("limit", 10)
                files = await drive_list_files(tokens, query=query, folder_id=folder_id, limit=limit)
                if not files:
                    return f"No files found{' for: ' + query if query else ''}."
                lines = [f"Google Drive files{' for ' + repr(query) if query else ''}:\n"]
                for f in files:
                    lines.append(
                        f"  {f.get('name', 'Untitled')} ({f.get('type', '')})\n"
                        f"    Modified: {f.get('modified', 'N/A')}\n"
                        f"    Link: {f.get('link', '')}"
                    )
                return "\n".join(lines)

            elif action == "read":
                file_id = params.get("file_id", "")
                if not file_id:
                    return "Missing 'file_id' to read."
                return f"File reading via Drive API requires file export — use the file link instead."

            return f"Unknown Drive action: '{action}'."
        except Exception as exc:
            return f"Google Drive error: {exc}"


# ═════════════════════════════════════════════════════════════════════════
# Slack tool
# ═════════════════════════════════════════════════════════════════════════

class SlackTool(BaseTool):
    """Interact with Slack — channels, messages, search."""

    name = "slack"
    description = (
        "Read Slack channels, send messages, or search.  "
        "Params: action (str: 'channels' | 'read' | 'send' | 'search'), "
        "channel? (str), text? (str), query? (str), limit? (int)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.slack_client import SlackClient

        action = params.get("action", "channels")
        client = SlackClient()

        if action == "channels":
            channels = await client.list_channels(limit=params.get("limit", 20))
            if not channels:
                return "No channels found or Slack not configured."
            lines = ["Slack channels:\n"]
            for ch in channels:
                topic = f" — {ch['topic']}" if ch.get("topic") else ""
                lines.append(f"  #{ch['name']}{topic}")
            return "\n".join(lines)

        elif action == "read":
            channel = params.get("channel", "")
            if not channel:
                return "Missing 'channel' to read."
            messages = await client.read_messages(channel, limit=params.get("limit", 10))
            if not messages:
                return f"No messages in channel '{channel}'."
            lines = [f"Messages from #{channel}:\n"]
            for m in messages:
                lines.append(f"  [{m.get('user', '?')}] {m.get('text', '')}")
            return "\n".join(lines)

        elif action == "send":
            channel = params.get("channel", "")
            text = params.get("text", "")
            if not channel or not text:
                return "Missing 'channel' and/or 'text'."
            result = await client.send_message(channel, text, thread_ts=params.get("thread_ts"))
            if result.get("error"):
                return f"Slack error: {result['error']}"
            return f"Message sent to #{channel}."

        elif action == "search":
            query = params.get("query", "")
            if not query:
                return "Missing 'query' for Slack search."
            results = await client.search_messages(query, count=params.get("limit", 5))
            if not results:
                return f"No Slack messages matching: '{query}'"
            lines = [f"Slack search for '{query}':\n"]
            for r in results:
                lines.append(
                    f"  [{r.get('user', '?')} in #{r.get('channel', '?')}] "
                    f"{r.get('text', '')[:200]}"
                )
            return "\n".join(lines)

        return f"Unknown Slack action: '{action}'."


# ═════════════════════════════════════════════════════════════════════════
# GitHub tool
# ═════════════════════════════════════════════════════════════════════════

class GitHubTool(BaseTool):
    """Interact with GitHub — repos, files, issues."""

    name = "github"
    description = (
        "Search repos, read files, manage issues on GitHub.  "
        "Params: action (str: 'search_repos' | 'repo_info' | 'read_file' | "
        "'list_issues' | 'create_issue'), owner? (str), repo? (str), "
        "query? (str), path? (str), title? (str), body? (str), labels? (list)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.github_client import GitHubClient

        action = params.get("action", "search_repos")
        client = GitHubClient()

        try:
            if action == "search_repos":
                query = params.get("query", "")
                if not query:
                    return "Missing 'query' for repo search."
                repos = await client.search_repos(query, max_results=params.get("max_results", 5))
                if not repos:
                    return f"No repos found for: '{query}'"
                lines = [f"GitHub repos for '{query}':\n"]
                for r in repos:
                    lines.append(
                        f"  {r['full_name']} ({r.get('language', '?')}, "
                        f"{r['stars']} stars)\n"
                        f"    {r.get('description', '')[:100]}"
                    )
                return "\n".join(lines)

            elif action == "repo_info":
                owner = params.get("owner", "")
                repo = params.get("repo", "")
                if not owner or not repo:
                    return "Missing 'owner' and/or 'repo'."
                info = await client.get_repo(owner, repo)
                return (
                    f"Repo: {info['full_name']}\n"
                    f"  Description: {info.get('description', 'N/A')}\n"
                    f"  Language: {info.get('language', 'N/A')}\n"
                    f"  Stars: {info['stars']} | Forks: {info['forks']} | "
                    f"Open Issues: {info['open_issues']}\n"
                    f"  URL: {info['url']}"
                )

            elif action == "read_file":
                owner = params.get("owner", "")
                repo = params.get("repo", "")
                path = params.get("path", "")
                if not owner or not repo or not path:
                    return "Missing 'owner', 'repo', and/or 'path'."
                result = await client.read_file(owner, repo, path, ref=params.get("ref"))
                return (
                    f"File: {result['path']} ({result['size']} bytes)\n"
                    f"Content:\n{result['content'][:5000]}"
                )

            elif action == "list_issues":
                owner = params.get("owner", "")
                repo = params.get("repo", "")
                if not owner or not repo:
                    return "Missing 'owner' and/or 'repo'."
                issues = await client.list_issues(
                    owner, repo,
                    state=params.get("state", "open"),
                    max_results=params.get("max_results", 10),
                )
                if not issues:
                    return f"No issues found for {owner}/{repo}."
                lines = [f"Issues for {owner}/{repo}:\n"]
                for i in issues:
                    labels = ", ".join(i.get("labels", []))
                    lines.append(
                        f"  #{i['number']}: {i['title']} [{i['state']}]\n"
                        f"    By: {i['user']} | Labels: {labels or 'none'}"
                    )
                return "\n".join(lines)

            elif action == "create_issue":
                owner = params.get("owner", "")
                repo = params.get("repo", "")
                title = params.get("title", "")
                if not owner or not repo or not title:
                    return "Missing 'owner', 'repo', and/or 'title'."
                result = await client.create_issue(
                    owner, repo, title,
                    body=params.get("body", ""),
                    labels=params.get("labels"),
                )
                if result.get("error"):
                    return f"GitHub error: {result['error']}"
                return (
                    f"Issue created: #{result['number']} — {result['title']}\n"
                    f"  URL: {result['url']}"
                )

            return f"Unknown GitHub action: '{action}'."
        except Exception as exc:
            return f"GitHub error: {exc}"


# ═════════════════════════════════════════════════════════════════════════
# Wolfram Alpha tool
# ═════════════════════════════════════════════════════════════════════════

class WolframAlphaTool(BaseTool):
    """Query Wolfram Alpha for computational knowledge."""

    name = "wolfram_alpha"
    description = (
        "Query Wolfram Alpha for math, science, geography, unit conversions, "
        "and other computational knowledge.  Params: query (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.wolfram import WolframClient

        query = params.get("query", "")
        if not query:
            return "No query provided."

        client = WolframClient()
        result = await client.query(query)

        if result.get("error"):
            return f"Wolfram Alpha error: {result['error']}"

        if not result.get("success"):
            suggestions = result.get("suggestions", [])
            hint = f"  Suggestions: {', '.join(suggestions)}" if suggestions else ""
            return f"Wolfram Alpha could not interpret: '{query}'.{hint}"

        lines: list[str] = [f"Wolfram Alpha results for: '{query}'\n"]
        for pod in result.get("pods", []):
            lines.append(f"  [{pod['title']}]\n  {pod['text']}")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Perplexity research tool
# ═════════════════════════════════════════════════════════════════════════

class PerplexityResearchTool(BaseTool):
    """Deep research using Perplexity's search-augmented LLM."""

    name = "perplexity_research"
    description = (
        "Perform deep research on a topic using Perplexity's search-augmented "
        "LLM.  Returns comprehensive, sourced answers.  "
        "Params: query (str), max_tokens? (int, default 1024)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.perplexity import PerplexityClient

        query = params.get("query", "")
        max_tokens = params.get("max_tokens", 1024)
        if not query:
            return "No research query provided."

        client = PerplexityClient()
        result = await client.research(query, max_tokens=max_tokens)

        if result.get("error"):
            return f"Perplexity error: {result['error']}"

        content = result.get("content", "")
        citations = result.get("citations", [])
        text = f"Research results for: '{query}'\n\n{content}"
        if citations:
            text += "\n\nSources:\n" + "\n".join(f"  - {c}" for c in citations)
        return text


# ═════════════════════════════════════════════════════════════════════════
# Financial data tool
# ═════════════════════════════════════════════════════════════════════════

class FinancialDataTool(BaseTool):
    """Get stock quotes and financial data from Alpha Vantage."""

    name = "financial_data"
    description = (
        "Get real-time stock quotes, search symbols, or get historical data.  "
        "Params: action (str: 'quote' | 'search' | 'daily'), "
        "symbol? (str, e.g. AAPL), keywords? (str, for search)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.alpha_vantage import AlphaVantageClient

        action = params.get("action", "quote")
        client = AlphaVantageClient()

        if action == "search":
            keywords = params.get("keywords", "")
            if not keywords:
                return "Missing 'keywords' for symbol search."
            result = await client.search_symbol(keywords)
            if result.get("error"):
                return f"Alpha Vantage error: {result['error']}"
            matches = result.get("bestMatches", [])
            if not matches:
                return f"No symbols found for: '{keywords}'"
            lines = [f"Symbol search for '{keywords}':\n"]
            for m in matches[:5]:
                lines.append(
                    f"  {m.get('1. symbol', '')} — {m.get('2. name', '')} "
                    f"({m.get('4. region', '')})"
                )
            return "\n".join(lines)

        elif action == "daily":
            symbol = params.get("symbol", "")
            if not symbol:
                return "Missing 'symbol' for daily data."
            result = await client.get_daily(symbol)
            if result.get("error"):
                return f"Alpha Vantage error: {result['error']}"
            ts = result.get("Time Series (Daily)", {})
            lines = [f"Daily data for {symbol} (last 5 days):\n"]
            for date, vals in list(ts.items())[:5]:
                lines.append(
                    f"  {date}: O={vals.get('1. open')} H={vals.get('2. high')} "
                    f"L={vals.get('3. low')} C={vals.get('4. close')} "
                    f"V={vals.get('5. volume')}"
                )
            return "\n".join(lines)

        else:  # quote
            symbol = params.get("symbol", "")
            if not symbol:
                return "Missing 'symbol' for quote."
            result = await client.get_quote(symbol)
            if result.get("error"):
                return f"Alpha Vantage error: {result['error']}"
            quote = result.get("Global Quote", {})
            if not quote:
                return f"No quote data for '{symbol}'."
            return (
                f"Stock quote for {quote.get('01. symbol', symbol)}:\n"
                f"  Price: ${quote.get('05. price', 'N/A')}\n"
                f"  Change: {quote.get('09. change', 'N/A')} "
                f"({quote.get('10. change percent', 'N/A')})\n"
                f"  Volume: {quote.get('06. volume', 'N/A')}\n"
                f"  Previous Close: ${quote.get('08. previous close', 'N/A')}"
            )


# ═════════════════════════════════════════════════════════════════════════
# Flight tracker tool
# ═════════════════════════════════════════════════════════════════════════

class FlightTrackerTool(BaseTool):
    """Track flights and get airport information."""

    name = "flight_tracker"
    description = (
        "Track flights by IATA code, search flights by route, or get airport "
        "info.  Params: action (str: 'track' | 'search' | 'airport'), "
        "flight_iata? (str, e.g. AA100), dep_iata? (str), arr_iata? (str), "
        "airline_iata? (str), iata_code? (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.flight_tracker import FlightTrackerClient

        action = params.get("action", "track")
        client = FlightTrackerClient()

        if action == "airport":
            code = params.get("iata_code", "")
            if not code:
                return "Missing 'iata_code' for airport info."
            result = await client.get_airport_info(code)
            if result.get("error"):
                return f"AviationStack error: {result['error']}"
            airports = result.get("data", [])
            if not airports:
                return f"No airport found for code '{code}'."
            ap = airports[0]
            return (
                f"Airport: {ap.get('airport_name', 'Unknown')}\n"
                f"  IATA: {ap.get('iata_code', '')}\n"
                f"  City: {ap.get('city_iata_code', '')} | "
                f"Country: {ap.get('country_name', '')}\n"
                f"  Timezone: {ap.get('timezone', '')}"
            )

        elif action == "search":
            result = await client.search_flights(
                dep_iata=params.get("dep_iata"),
                arr_iata=params.get("arr_iata"),
                airline_iata=params.get("airline_iata"),
            )
            if result.get("error"):
                return f"AviationStack error: {result['error']}"
            flights = result.get("data", [])[:5]
            if not flights:
                return "No flights found matching criteria."
            lines = ["Flights found:\n"]
            for f in flights:
                dep = f.get("departure", {})
                arr = f.get("arrival", {})
                lines.append(
                    f"  {f.get('flight', {}).get('iata', '?')}: "
                    f"{dep.get('iata', '?')} -> {arr.get('iata', '?')} | "
                    f"Status: {f.get('flight_status', 'unknown')}"
                )
            return "\n".join(lines)

        else:  # track
            flight_iata = params.get("flight_iata", "")
            if not flight_iata:
                return "Missing 'flight_iata' for tracking."
            result = await client.track_flight(flight_iata)
            if result.get("error"):
                return f"AviationStack error: {result['error']}"
            flights = result.get("data", [])
            if not flights:
                return f"No data found for flight '{flight_iata}'."
            fl = flights[0]
            dep = fl.get("departure", {})
            arr = fl.get("arrival", {})
            return (
                f"Flight {fl.get('flight', {}).get('iata', flight_iata)}:\n"
                f"  Status: {fl.get('flight_status', 'unknown')}\n"
                f"  From: {dep.get('airport', '?')} ({dep.get('iata', '')})\n"
                f"  To: {arr.get('airport', '?')} ({arr.get('iata', '')})\n"
                f"  Scheduled departure: {dep.get('scheduled', 'N/A')}\n"
                f"  Scheduled arrival: {arr.get('scheduled', 'N/A')}"
            )


# ═════════════════════════════════════════════════════════════════════════
# Google Maps tool
# ═════════════════════════════════════════════════════════════════════════

class GoogleMapsTool(BaseTool):
    """Get directions, geocode addresses, and search places via Google Maps."""

    name = "google_maps"
    description = (
        "Geocode addresses, get directions, search places, or calculate "
        "distances via Google Maps.  Params: action (str: 'geocode' | "
        "'directions' | 'places' | 'distance_matrix'), "
        "address? (str), origin? (str), destination? (str), "
        "query? (str), mode? (str: driving/walking/transit/bicycling)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.google_maps import GoogleMapsClient

        action = params.get("action", "geocode")
        client = GoogleMapsClient()

        if action == "geocode":
            address = params.get("address", "")
            if not address:
                return "Missing 'address' for geocoding."
            result = await client.geocode(address)
            if result.get("error"):
                return f"Google Maps error: {result['error']}"
            results = result.get("results", [])
            if not results:
                return f"No results for address: '{address}'"
            loc = results[0]
            geo = loc.get("geometry", {}).get("location", {})
            return (
                f"Geocode result for: '{address}'\n"
                f"  Formatted: {loc.get('formatted_address', '')}\n"
                f"  Lat: {geo.get('lat', '')}, Lng: {geo.get('lng', '')}"
            )

        elif action == "directions":
            origin = params.get("origin", "")
            destination = params.get("destination", "")
            mode = params.get("mode", "driving")
            if not origin or not destination:
                return "Missing 'origin' and/or 'destination'."
            result = await client.directions(origin, destination, mode)
            if result.get("error"):
                return f"Google Maps error: {result['error']}"
            routes = result.get("routes", [])
            if not routes:
                return "No route found."
            leg = routes[0].get("legs", [{}])[0]
            return (
                f"Directions ({mode}): {origin} -> {destination}\n"
                f"  Distance: {leg.get('distance', {}).get('text', 'N/A')}\n"
                f"  Duration: {leg.get('duration', {}).get('text', 'N/A')}\n"
                f"  Start: {leg.get('start_address', '')}\n"
                f"  End: {leg.get('end_address', '')}"
            )

        elif action == "places":
            query = params.get("query", "")
            if not query:
                return "Missing 'query' for places search."
            result = await client.places_search(query)
            if result.get("error"):
                return f"Google Maps error: {result['error']}"
            places = result.get("results", [])[:5]
            if not places:
                return f"No places found for: '{query}'"
            lines = [f"Places for '{query}':\n"]
            for p in places:
                rating = p.get("rating", "N/A")
                lines.append(
                    f"  {p.get('name', 'Unknown')}: "
                    f"{p.get('formatted_address', '')} "
                    f"(rating: {rating})"
                )
            return "\n".join(lines)

        elif action == "distance_matrix":
            origins = params.get("origins", params.get("origin", ""))
            destinations = params.get("destinations", params.get("destination", ""))
            mode = params.get("mode", "driving")
            if not origins or not destinations:
                return "Missing 'origins' and/or 'destinations'."
            result = await client.distance_matrix(origins, destinations, mode)
            if result.get("error"):
                return f"Google Maps error: {result['error']}"
            rows = result.get("rows", [])
            if not rows:
                return "No distance data found."
            elements = rows[0].get("elements", [{}])
            el = elements[0] if elements else {}
            return (
                f"Distance ({mode}): {origins} -> {destinations}\n"
                f"  Distance: {el.get('distance', {}).get('text', 'N/A')}\n"
                f"  Duration: {el.get('duration', {}).get('text', 'N/A')}"
            )

        return f"Unknown Google Maps action: '{action}'."


# ═════════════════════════════════════════════════════════════════════════
# Nutrition & Recipe tool
# ═════════════════════════════════════════════════════════════════════════

class NutritionRecipeTool(BaseTool):
    """Search recipes and get nutrition data via Edamam."""

    name = "nutrition_recipe"
    description = (
        "Search for recipes or get nutrition info for ingredients.  "
        "Params: action (str: 'recipe' | 'nutrition'), "
        "query (str), diet? (str), health? (str), cuisine_type? (str), "
        "max_results? (int, default 5)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.edamam import EdamamClient

        action = params.get("action", "recipe")
        query = params.get("query", "")
        if not query:
            return "No query provided."

        client = EdamamClient()

        if action == "nutrition":
            result = await client.get_nutrition(query)
            if result.get("error"):
                return f"Edamam error: {result['error']}"
            calories = result.get("calories", 0)
            nutrients = result.get("nutrients", {})
            lines = [f"Nutrition for: '{query}'\n  Calories: {calories}"]
            for key in ("FAT", "CHOCDF", "PROCNT", "FIBTG", "SUGAR"):
                n = nutrients.get(key)
                if n:
                    lines.append(f"  {n['label']}: {n['quantity']} {n['unit']}")
            return "\n".join(lines)

        else:  # recipe
            max_results = params.get("max_results", 5)
            result = await client.search_recipes(
                query,
                diet=params.get("diet"),
                health=params.get("health"),
                cuisine_type=params.get("cuisine_type"),
                max_results=max_results,
            )
            if result.get("error"):
                return f"Edamam error: {result['error']}"
            recipes = result.get("recipes", [])
            if not recipes:
                return f"No recipes found for: '{query}'"
            lines = [f"Recipes for '{query}' ({result.get('count', 0)} total):\n"]
            for i, r in enumerate(recipes, 1):
                lines.append(
                    f"  {i}. {r['label']} ({r['calories']} cal, "
                    f"{r['servings']} servings)\n"
                    f"     Source: {r['source']}\n"
                    f"     URL: {r['url']}"
                )
            return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Morning Routine tools
# ═════════════════════════════════════════════════════════════════════════

class SetWakeTimeTool(BaseTool):
    """Set or change the morning routine wake time."""

    name = "set_wake_time"
    description = (
        "Set or change Mr. Stark's morning routine wake time. "
        "Use when he says things like 'wake me up at 7' or 'set my alarm for 6:30'. "
        "Params: time (str, e.g. '07:00' or '6:45')."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.db.redis import get_redis_client

        time_str = params.get("time", "").strip()
        if not time_str:
            return "Missing required 'time' parameter."

        # Normalise to HH:MM
        parts = time_str.replace(".", ":").split(":")
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            normalised = f"{hour:02d}:{minute:02d}"
        except (ValueError, IndexError):
            return f"Invalid time format: '{time_str}'. Use HH:MM (e.g. '07:00')."

        r = await get_redis_client()
        await r.cache_set("jarvis:morning:wake_time", normalised, ttl=86400 * 365)

        return f"Morning routine wake time set to {normalised} Mountain Time."


# ═════════════════════════════════════════════════════════════════════════
# Send iMessage (via Mac Mini Agent)
# ═════════════════════════════════════════════════════════════════════════

class SendIMessageTool(BaseTool):
    """Send an iMessage via the Mac Mini agent service."""

    name = "send_imessage"
    description = (
        "Send an iMessage to a phone number or Apple ID. "
        "This sends FROM JARVIS's Mac Mini — NEVER from the user's account. "
        "Params: to (str: phone number or Apple ID), text (str: message text)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.mac_mini import send_imessage, is_configured

        if not is_configured():
            return (
                "Mac Mini agent is not configured. "
                "MAC_MINI_AGENT_URL and MAC_MINI_AGENT_KEY need to be set on Railway."
            )

        to = params.get("to", "").strip()
        text = params.get("text", "").strip()

        if not to or not text:
            return "Both 'to' (phone number or Apple ID) and 'text' are required."

        result = await send_imessage(to=to, text=text)

        if result.get("success"):
            return f"iMessage sent to {result.get('recipient', to)}."
        else:
            return f"Failed to send iMessage: {result.get('message', 'Unknown error')}"


# ═════════════════════════════════════════════════════════════════════════
# Sports (ESPN) tool
# ═════════════════════════════════════════════════════════════════════════

class SportsTool(BaseTool):
    """Get sports scores, schedules, and standings via ESPN."""

    name = "sports"
    description = (
        "Get sports scores, schedules, standings, and team info via ESPN. "
        "Supports college football (BYU, etc.), NFL, NBA, MLB, NHL. "
        "Params: action (str: 'scores' | 'schedule' | 'standings' | 'team'), "
        "team? (str), sport? (str, default 'football')."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.sports import (
            get_scoreboard,
            get_schedule,
            get_standings,
            get_team_info,
        )

        action = params.get("action", "scores")
        team = params.get("team", "BYU")
        sport = params.get("sport", "football")

        try:
            if action == "team":
                info = await get_team_info(team, sport)
                lines = [
                    f"{info['name']} ({info['abbreviation']})",
                    f"  Record: {info['record']}",
                ]
                if info.get("standing"):
                    lines.append(f"  Standing: {info['standing']}")
                if info.get("next_game"):
                    ng = info["next_game"]
                    lines.append(f"  Next game: {ng.get('shortName', ng.get('name', 'TBD'))} — {ng.get('date', 'TBD')}")
                return "\n".join(lines)

            elif action == "schedule":
                season = params.get("season", "")
                games = await get_schedule(team, sport, season)
                if not games:
                    return f"No schedule found for {team} ({sport})."
                lines = [f"{team.upper()} {sport.title()} Schedule:\n"]
                for g in games[:15]:
                    status = g["result"] if g["completed"] else "Upcoming"
                    lines.append(f"  {g['shortName'] or g['name']}: {status} — {g['date'][:10]}")
                return "\n".join(lines)

            elif action == "standings":
                group = params.get("group", "")
                standings = await get_standings(sport, group)
                if not standings:
                    return f"No standings data found for {sport}."
                lines = [f"{sport.title()} Standings:\n"]
                current_group = ""
                for s in standings[:30]:
                    if s["group"] != current_group:
                        current_group = s["group"]
                        lines.append(f"\n  {current_group}:")
                    conf = f" (Conf: {s['conference']})" if s.get("conference") else ""
                    lines.append(f"    {s['team']}: {s.get('overall', f'{s.get(\"wins\", \"?\")}-{s.get(\"losses\", \"?\")}')}{conf}")
                return "\n".join(lines)

            else:  # scores / scoreboard
                groups = params.get("groups", "")
                limit = params.get("limit", 10)
                games = await get_scoreboard(sport, groups, limit)
                if not games:
                    return f"No games on the scoreboard right now for {sport}."
                lines = [f"{sport.title()} Scoreboard:\n"]
                for g in games:
                    teams_str = " vs ".join(
                        f"{t['name']} {t['score']}" for t in g.get("teams", [])
                    )
                    lines.append(f"  {teams_str} — {g['status']}")
                return "\n".join(lines)

        except ValueError as e:
            return str(e)
        except Exception as e:
            logger.exception("Sports tool error")
            return f"Sports lookup failed: {e}"


# ═════════════════════════════════════════════════════════════════════════
# Scripture Lookup tool
# ═════════════════════════════════════════════════════════════════════════

class ScriptureLookupTool(BaseTool):
    """Look up Bible and LDS scripture verses."""

    name = "scripture_lookup"
    description = (
        "Look up scripture verses from the Bible (KJV) or LDS scriptures "
        "(Book of Mormon, Doctrine & Covenants, Pearl of Great Price). "
        "Params: reference (str, e.g. 'John 3:16', '1 Nephi 3:7', 'D&C 121:7-8')."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.scriptures import lookup_scripture

        reference = params.get("reference", "").strip()
        if not reference:
            return "Missing 'reference' parameter. Provide a scripture reference like 'John 3:16' or '1 Nephi 3:7'."

        try:
            result = await lookup_scripture(reference)

            if result.get("error"):
                return f"Scripture lookup error: {result['error']}"

            lines = [f"{result.get('reference', reference)}"]
            if result.get("translation"):
                lines[0] += f" ({result['translation']})"

            text = result.get("text", "")
            if text:
                lines.append(text)

            if result.get("url"):
                lines.append(f"\nSource: {result.get('source', 'churchofjesuschrist.org')}")
                lines.append(result["url"])

            return "\n".join(lines)

        except Exception as e:
            logger.exception("Scripture lookup error")
            return f"Scripture lookup failed: {e}"


# ═════════════════════════════════════════════════════════════════════════
# Navigate tool (Find My location → Google Maps directions)
# ═════════════════════════════════════════════════════════════════════════

class NavigateTool(BaseTool):
    """Get navigation distance/time from user's current location to a destination."""

    name = "navigate"
    description = (
        "Get driving distance and time from Mr. Stark's current location to a "
        "destination. Uses Find My on the Mac Mini for live location, then "
        "Google Maps for directions. Can disambiguate destination names "
        "(e.g. 'La Jolla' could be a nearby restaurant or the city in CA). "
        "Params: destination (str), mode? (str: driving/walking/transit, default driving)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.mac_mini import get_location, is_configured as mini_configured
        from app.integrations.google_maps import GoogleMapsClient

        destination = params.get("destination", "").strip()
        mode = params.get("mode", "driving")
        if not destination:
            return "Missing 'destination' parameter."

        # Step 1: Get user's current location from Mac Mini Find My
        origin_str = ""
        if mini_configured():
            loc = await get_location()
            if loc.get("found"):
                lat, lng = loc["latitude"], loc["longitude"]
                origin_str = f"{lat},{lng}"
                logger.info(
                    "NAVIGATE: Got location (%.4f, %.4f) source=%s updated=%s",
                    lat, lng, loc.get("source", "?"), loc.get("updated_at", "?"),
                )
            else:
                logger.warning("NAVIGATE: Location not found: %s", loc.get("error", "unknown"))

        if not origin_str:
            # Fallback: Orem, UT (user's home area)
            origin_str = "40.2969,-111.6946"
            logger.info("NAVIGATE: Using fallback location (Orem, UT)")

        maps = GoogleMapsClient()

        # Step 2: Search for the destination to find possible matches
        places_result = await maps.places_search(
            destination,
            location=origin_str,
            radius=50000,  # 50km radius for nearby matches
        )

        nearby_matches = []
        if not places_result.get("error"):
            for p in places_result.get("results", [])[:3]:
                ploc = p.get("geometry", {}).get("location", {})
                nearby_matches.append({
                    "name": p.get("name", ""),
                    "address": p.get("formatted_address", ""),
                    "lat": ploc.get("lat"),
                    "lng": ploc.get("lng"),
                    "rating": p.get("rating"),
                    "types": p.get("types", []),
                })

        # Step 3: Get directions to the destination (as typed)
        dir_result = await maps.directions(origin_str, destination, mode)
        if dir_result.get("error"):
            # If directions fail, try with the first place match
            if nearby_matches:
                dest_coords = f"{nearby_matches[0]['lat']},{nearby_matches[0]['lng']}"
                dir_result = await maps.directions(origin_str, dest_coords, mode)

        lines = [f"Navigation to: {destination} ({mode})\n"]

        # Main route
        routes = dir_result.get("routes", [])
        if routes:
            leg = routes[0].get("legs", [{}])[0]
            dist = leg.get("distance", {}).get("text", "N/A")
            dur = leg.get("duration", {}).get("text", "N/A")
            end_addr = leg.get("end_address", destination)
            lines.append(f"  Distance: {dist}")
            lines.append(f"  ETA: {dur}")
            lines.append(f"  Destination: {end_addr}")
        else:
            lines.append("  Could not calculate route to this destination.")

        # Show nearby disambiguation if there are interesting alternatives
        if len(nearby_matches) > 1:
            lines.append(f"\n  Other matches nearby:")
            for m in nearby_matches[:3]:
                rating_str = f" (rating: {m['rating']})" if m.get("rating") else ""
                lines.append(f"    - {m['name']}: {m['address']}{rating_str}")

                # Get distance to each alternative
                if m.get("lat") and m.get("lng"):
                    alt_result = await maps.distance_matrix(
                        origin_str, f"{m['lat']},{m['lng']}", mode
                    )
                    if not alt_result.get("error"):
                        rows = alt_result.get("rows", [])
                        if rows:
                            el = rows[0].get("elements", [{}])[0]
                            alt_dist = el.get("distance", {}).get("text", "")
                            alt_dur = el.get("duration", {}).get("text", "")
                            if alt_dist:
                                lines.append(f"      {alt_dist}, {alt_dur}")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Mac Mini Remote Exec tool
# ═════════════════════════════════════════════════════════════════════════

class MacMiniExecTool(BaseTool):
    """Execute shell commands on the Mac Mini remotely."""

    name = "mac_mini_exec"
    description = (
        "Run a shell command on the Mac Mini. Full remote access — can install "
        "packages, manage files, check logs, run scripts, admin the system. "
        "Params: command (str), working_dir? (str), timeout? (int, default 120)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.mac_mini import remote_exec, is_configured

        if not is_configured():
            return "Mac Mini agent not configured."

        command = params.get("command", "").strip()
        if not command:
            return "Missing 'command' parameter."

        result = await remote_exec(
            command=command,
            working_dir=params.get("working_dir", ""),
            timeout=params.get("timeout", 120),
        )

        lines = []
        if result.get("success"):
            lines.append(f"Command succeeded (exit 0, {result.get('duration_ms', 0):.0f}ms)")
        else:
            lines.append(f"Command failed (exit {result.get('exit_code', -1)}, {result.get('duration_ms', 0):.0f}ms)")

        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        if stdout:
            lines.append(f"\nstdout:\n{stdout[:10000]}")
        if stderr:
            lines.append(f"\nstderr:\n{stderr[:5000]}")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Mac Mini Claude Code tool
# ═════════════════════════════════════════════════════════════════════════

class MacMiniClaudeCodeTool(BaseTool):
    """Run Claude Code on the Mac Mini with full permissions."""

    name = "mac_mini_claude_code"
    description = (
        "Run Claude Code (claude CLI) on the Mac Mini with full autonomous "
        "permissions. Use for development tasks, file management, system "
        "configuration, or any complex multi-step task on the Mini. "
        "Params: prompt (str), working_dir? (str), timeout? (int, default 600), model? (str)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.mac_mini import run_claude_code, is_configured

        if not is_configured():
            return "Mac Mini agent not configured."

        prompt = params.get("prompt", "").strip()
        if not prompt:
            return "Missing 'prompt' parameter."

        result = await run_claude_code(
            prompt=prompt,
            working_dir=params.get("working_dir", ""),
            timeout=params.get("timeout", 600),
            model=params.get("model", ""),
        )

        lines = []
        if result.get("success"):
            lines.append(f"Claude Code completed (exit 0, {result.get('duration_ms', 0):.0f}ms)")
        else:
            lines.append(f"Claude Code failed (exit {result.get('exit_code', -1)}, {result.get('duration_ms', 0):.0f}ms)")

        output = result.get("output", "").strip()
        if output:
            lines.append(f"\n{output[:20000]}")

        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Mac Mini Screenshot tool
# ═════════════════════════════════════════════════════════════════════════

class MacMiniScreenshotTool(BaseTool):
    """Capture a screenshot from the Mac Mini's display."""

    name = "mac_mini_screenshot"
    description = (
        "Take a screenshot of the Mac Mini's screen. Returns a base64 PNG "
        "image. Use to see what's currently displayed on the Mini. "
        "Params: thumbnail? (bool, default true)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.mac_mini import take_screenshot, is_configured

        if not is_configured():
            return "Mac Mini agent not configured."

        result = await take_screenshot(
            thumbnail=params.get("thumbnail", True),
        )

        if result.get("error"):
            return f"Screenshot failed: {result['error']}"

        size = result.get("size_bytes", 0)
        b64 = result.get("image_base64", "")

        return (
            f"Screenshot captured ({size:,} bytes).\n"
            f"Base64 PNG data ({len(b64)} chars) — use this in vision-capable "
            f"models or save to file for viewing."
        )


# ═════════════════════════════════════════════════════════════════════════
# Tool registry factory
# ═════════════════════════════════════════════════════════════════════════

_registry: Optional[dict[str, BaseTool]] = None


def get_tool_registry() -> dict[str, BaseTool]:
    """Return the singleton tool registry mapping name -> BaseTool instance."""
    global _registry
    if _registry is None:
        tools: list[BaseTool] = [
            SearchKnowledgeTool(),
            SendEmailTool(),
            ReadEmailTool(),
            SendJarvisEmailTool(),
            CreateCalendarEventTool(),
            ListCalendarEventsTool(),
            SetReminderTool(),
            SmartHomeControlTool(),
            WebSearchTool(),
            WeatherTool(),
            NewsTool(),
            SpotifyTool(),
            CalculatorTool(),
            DateTimeTool(),
            # iMCP — native macOS tools (no API keys, all local)
            IMCPCalendarListTool(),
            IMCPEventsFetchTool(),
            IMCPEventsCreateTool(),
            IMCPContactsMeTool(),
            IMCPContactsSearchTool(),
            IMCPContactsCreateTool(),
            IMCPMessagesFetchTool(),
            IMCPRemindersListsTool(),
            IMCPRemindersFetchTool(),
            IMCPRemindersCreateTool(),
            IMCPLocationCurrentTool(),
            IMCPLocationGeocodeTool(),
            IMCPMapsSearchTool(),
            IMCPMapsDirectionsTool(),
            IMCPMapsETATool(),
            IMCPWeatherCurrentTool(),
            IMCPWeatherForecastTool(),
            # MCP integrations (Google Drive, Slack, GitHub)
            GoogleDriveTool(),
            SlackTool(),
            GitHubTool(),
            # External API integrations
            WolframAlphaTool(),
            PerplexityResearchTool(),
            FinancialDataTool(),
            FlightTrackerTool(),
            GoogleMapsTool(),
            NutritionRecipeTool(),
            # Morning routine
            SetWakeTimeTool(),
            # Mac Mini agent
            SendIMessageTool(),
            # Quick-win integrations (free, no API key)
            SportsTool(),
            ScriptureLookupTool(),
            # Navigation (Find My + Google Maps)
            NavigateTool(),
            # Mac Mini remote control
            MacMiniExecTool(),
            MacMiniClaudeCodeTool(),
            MacMiniScreenshotTool(),
        ]
        _registry = {t.name: t for t in tools}
    return _registry


def get_tool_descriptions() -> list[dict[str, str]]:
    """Return a list of ``{"name": ..., "description": ...}`` dicts for
    every registered tool.  Useful for capability listings and the MCP
    capabilities endpoint."""
    registry = get_tool_registry()
    return [
        {"name": t.name, "description": t.description}
        for t in registry.values()
    ]
