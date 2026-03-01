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
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.state import AgentState

logger = logging.getLogger("jarvis.agents.tools")


# ═════════════════════════════════════════════════════════════════════════
# Base class
# ═════════════════════════════════════════════════════════════════════════

class BaseTool(ABC):
    """Abstract base for all JARVIS tools."""

    name: str = ""
    description: str = ""

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
        "emails, messages) using semantic search.  Params: query (str), "
        "limit? (int, default 5)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.db.qdrant import get_qdrant_store
        from openai import AsyncOpenAI
        from app.config import settings

        query = params.get("query", "")
        limit = params.get("limit", 5)
        if not query:
            return "No search query provided."

        # Generate embedding
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        embed_resp = await client.embeddings.create(
            input=query,
            model="text-embedding-3-small",
        )
        vector = embed_resp.data[0].embedding

        store = get_qdrant_store()
        user_id = (state or {}).get("user_id", "")
        filters = {"user_id": user_id} if user_id else None
        results = await store.search(
            query_vector=vector,
            limit=limit,
            filter_conditions=filters,
            score_threshold=0.5,
        )

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
        from app.integrations.gmail import GmailClient

        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")
        cc = params.get("cc")
        bcc = params.get("bcc")

        if not to or not subject:
            return "Missing required email fields (to, subject)."

        async with GmailClient() as gmail:
            result = await gmail.send_email(
                to=to, subject=subject, body=body, cc=cc, bcc=bcc,
            )

        return (
            f"Email sent successfully.\n"
            f"  To: {result.get('to', to)}\n"
            f"  Subject: {result.get('subject', subject)}\n"
            f"  Message ID: {result.get('message_id', 'N/A')}"
        )


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
        from app.integrations.gmail import GmailClient

        query = params.get("query", "")
        limit = params.get("limit", 5)

        async with GmailClient() as gmail:
            emails = await gmail.read_emails(query=query, max_results=limit)

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
        from app.integrations.calendar import CalendarClient

        title = params.get("title", "")
        start = params.get("start", "")
        end = params.get("end", "")
        description = params.get("description", "")
        location = params.get("location")
        attendees = params.get("attendees")

        if not title or not start or not end:
            return "Missing required fields (title, start, end)."

        async with CalendarClient() as cal:
            result = await cal.create_event(
                title=title,
                start=start,
                end=end,
                description=description,
                location=location,
                attendees=attendees,
            )

        return (
            f"Calendar event created.\n"
            f"  Title: {result.get('title', title)}\n"
            f"  Start: {result.get('start', start)}\n"
            f"  End: {result.get('end', end)}\n"
            f"  Event ID: {result.get('event_id', 'N/A')}"
        )


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
        from app.integrations.calendar import CalendarClient

        start_date = params.get("start_date", "")
        end_date = params.get("end_date", "")
        if not start_date or not end_date:
            return "Missing required fields (start_date, end_date)."

        async with CalendarClient() as cal:
            events = await cal.list_events(
                start_date=start_date, end_date=end_date,
            )

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
        "Search the web for up-to-date information.  "
        "Params: query (str), max_results? (int, default 5)."
    )

    async def execute(
        self,
        params: dict[str, Any],
        *,
        state: Optional[AgentState] = None,
    ) -> str:
        from app.integrations.web_search import WebSearchClient

        query = params.get("query", "")
        max_results = params.get("max_results", 5)
        if not query:
            return "No search query provided."

        async with WebSearchClient() as client:
            results = await client.search(query=query, max_results=max_results)

        if not results:
            return f"No results found for: '{query}'"

        lines: list[str] = [f"Web search results for: '{query}'\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            snippet = result.get("snippet", "")[:300]
            lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

        return "\n".join(lines)


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
        tz_name = params.get("timezone", "UTC")

        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            return f"Unknown timezone: '{tz_name}'.  Use IANA names (e.g. 'US/Eastern', 'Europe/London')."

        now = datetime.now(tz=tz)

        if operation == "now":
            return (
                f"Current date/time ({tz_name}):\n"
                f"  Date:  {now.strftime('%A, %B %d, %Y')}\n"
                f"  Time:  {now.strftime('%I:%M:%S %p %Z')}\n"
                f"  ISO:   {now.isoformat()}\n"
                f"  Unix:  {int(now.timestamp())}"
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
