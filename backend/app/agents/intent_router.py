"""Ultra-fast intent routing via Cerebras inference.

Classifies user messages into tool categories in <100ms so the main
LLM (Gemini/Claude) only receives relevant tool definitions.
This prevents token waste and confusion from sending 39+ tools every request.
"""

from __future__ import annotations

import logging
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger("jarvis.intent_router")

# Tool categories with their constituent tools
TOOL_CATEGORIES = {
    "general": {
        "description": "General conversation, greetings, questions that don't need tools",
        "tools": [],
    },
    "knowledge": {
        "description": "Questions about the user's personal info, history, preferences, memories",
        "tools": ["search_knowledge"],
    },
    "email": {
        "description": "Reading, sending, or managing email",
        "tools": ["send_email", "read_email", "send_jarvis_email"],
    },
    "calendar": {
        "description": "Calendar events, scheduling, availability",
        "tools": ["create_calendar_event", "list_calendar_events", "mac_calendars_list", "mac_events_fetch", "mac_events_create"],
    },
    "weather": {
        "description": "Weather conditions, forecasts, temperature",
        "tools": ["weather", "mac_weather_current", "mac_weather_forecast"],
    },
    "navigation": {
        "description": "Directions, maps, travel time, distance, places, location, how far, navigate",
        "tools": ["navigate", "google_maps", "mac_maps_search", "mac_maps_directions", "mac_maps_eta", "mac_location_current", "mac_location_geocode"],
    },
    "web_search": {
        "description": "Searching the internet, looking up current information, research",
        "tools": ["web_search", "perplexity_research"],
    },
    "finance": {
        "description": "Stock prices, market data, financial information, crypto, forex",
        "tools": ["financial_data"],
    },
    "travel": {
        "description": "Flights, hotels, flight tracking, travel planning",
        "tools": ["flight_tracker"],
    },
    "smart_home": {
        "description": "Lights, thermostat, smart home devices, HomeKit",
        "tools": ["smart_home_control"],
    },
    "contacts": {
        "description": "Contact information, people lookup, phone numbers",
        "tools": ["mac_contacts_me", "mac_contacts_search", "mac_contacts_create"],
    },
    "messages": {
        "description": "iMessage, SMS, text messages, send a message, send a text",
        "tools": ["mac_messages_fetch", "send_imessage"],
    },
    "reminders": {
        "description": "Reminders, to-do lists, tasks",
        "tools": ["set_reminder", "mac_reminders_lists", "mac_reminders_fetch", "mac_reminders_create"],
    },
    "code_dev": {
        "description": "GitHub, code, repositories, pull requests, issues",
        "tools": ["github"],
    },
    "files": {
        "description": "Google Drive files, documents, uploads, file search",
        "tools": ["google_drive"],
    },
    "math_compute": {
        "description": "Math calculations, unit conversions, scientific queries",
        "tools": ["calculator", "wolfram_alpha"],
    },
    "datetime": {
        "description": "Current date, time, timezone conversions, time-related questions",
        "tools": ["date_time"],
    },
    "news": {
        "description": "News headlines, current events, articles",
        "tools": ["news"],
    },
    "music": {
        "description": "Music playback, playlists, songs, artists",
        "tools": ["spotify"],
    },
    "nutrition": {
        "description": "Recipes, nutrition info, food, cooking",
        "tools": ["nutrition_recipe"],
    },
    "communication": {
        "description": "Slack messages, team communication",
        "tools": ["slack"],
    },
    "morning_routine": {
        "description": "Morning routine, wake time, alarm, wake up time",
        "tools": ["set_wake_time"],
    },
    "sports": {
        "description": "Sports scores, games, schedules, standings, BYU, football, basketball, NFL, NBA",
        "tools": ["sports"],
    },
    "scripture": {
        "description": "Bible verses, Book of Mormon, scriptures, D&C, Pearl of Great Price, LDS",
        "tools": ["scripture_lookup"],
    },
    "mac_mini": {
        "description": "Mac Mini control, remote commands, SSH, shell, screenshot, Claude Code on the Mini, system admin",
        "tools": ["mac_mini_exec", "mac_mini_claude_code", "mac_mini_screenshot"],
    },
    "research": {
        "description": "Research briefing, what has JARVIS been learning, research findings, continuous learning updates",
        "tools": ["research_briefing"],
    },
}

_CATEGORY_LIST = "\n".join(
    f"- {name}: {info['description']}" for name, info in TOOL_CATEGORIES.items()
)

_ROUTER_SYSTEM_PROMPT = f"""You are an intent classifier. Given a user message, output ONLY the category names that apply (comma-separated, no spaces). If multiple categories apply, list all of them. If no tools are needed, output "general".

Categories:
{_CATEGORY_LIST}

Rules:
- Output ONLY category names, nothing else
- Multiple categories are comma-separated: "weather,calendar"
- "general" means no tools needed (casual chat, greetings, opinions)
- When in doubt, include the category
- Be fast, be precise"""

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client:
        return _client
    if not settings.CEREBRAS_API_KEY:
        return None
    _client = AsyncOpenAI(
        api_key=settings.CEREBRAS_API_KEY,
        base_url="https://api.cerebras.ai/v1",
    )
    return _client


async def route_intent(message: str) -> list[str]:
    """Classify a user message into tool categories.

    Returns a list of tool names that should be sent with the request.
    Returns empty list if no tools needed (general conversation) or
    if Cerebras is unavailable (falls back to sending all tools).
    """
    client = _get_client()
    if not client:
        logger.debug("Cerebras not configured — sending all tools")
        return []  # empty = send all tools (fallback)

    models = ["qwen-3-235b-a22b-instruct-2507", "gpt-oss-120b"]

    for model in models:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                max_tokens=50,
                temperature=0,
            )

            raw = response.choices[0].message.content.strip().lower()
            # Handle <think>...</think> tags from reasoning models
            if "<think>" in raw:
                # Extract content after </think>
                think_end = raw.rfind("</think>")
                if think_end != -1:
                    raw = raw[think_end + 8:].strip()

            categories = [c.strip() for c in raw.split(",") if c.strip()]

            if "general" in categories and len(categories) == 1:
                logger.info("Intent: general (no tools needed)")
                return []

            # Collect all tools from matched categories
            tools: list[str] = []
            for cat in categories:
                if cat in TOOL_CATEGORIES:
                    tools.extend(TOOL_CATEGORIES[cat]["tools"])

            # Always include knowledge search for context
            if "search_knowledge" not in tools and categories != ["general"]:
                tools.append("search_knowledge")

            logger.info("Intent categories: %s → %d tools", categories, len(tools))
            return list(set(tools))  # deduplicate

        except Exception as exc:
            logger.warning("Cerebras %s failed: %s — trying fallback", model, exc)
            continue

    logger.warning("All Cerebras models failed — sending all tools")
    return []  # fallback to all tools


def get_tools_for_intent(tool_names: list[str], all_tools: list[dict]) -> list[dict]:
    """Filter tool definitions to only those matching the routed intent.

    If tool_names is empty, returns all tools (fallback behavior).
    """
    if not tool_names:
        return all_tools
    name_set = set(tool_names)
    return [t for t in all_tools if t["name"] in name_set]


# ═══════════════════════════════════════════════════════════════════════════
# Sports sub-intent classification (Cerebras)
# ═══════════════════════════════════════════════════════════════════════════

_SPORTS_ROUTER_PROMPT = """You are a sports query classifier. Given a user message about sports, extract structured intent.

Output ONLY valid JSON with these fields:
- "sub_intent": one of "live_scores", "recent_result", "schedule", "standings", "historical", "general"
- "team": team name mentioned (e.g. "BYU", "Utah", "Lakers") or "" if none
- "sport": sport/league (e.g. "basketball", "football", "nba", "nfl", "mlb") or "" if unclear

Sub-intent definitions:
- "live_scores": asking about a game happening right now or today
- "recent_result": asking about a game that already happened (last night, yesterday, last game, how did they do)
- "schedule": asking about upcoming games, when they play next
- "standings": asking about rankings, standings, conference position
- "historical": asking about past seasons, last year, records, history, "how did they do last season"
- "general": any other sports question (trades, rumors, player stats, injuries, draft)

Rules:
- Output ONLY the JSON object, nothing else
- "recent_result" = the user wants to know the outcome of a specific recent game
- "historical" = anything about a past season or time period (not the current one)
- "general" = anything that needs a web search to answer properly
- When in doubt between "recent_result" and "historical", pick "historical" (safer — triggers web search)
- If the user says "how did X do" without specifying a timeframe, use "recent_result"
- If the user says "how did X do last year/season", use "historical"

Examples:
"Did BYU win?" → {"sub_intent": "recent_result", "team": "BYU", "sport": "basketball"}
"BYU football schedule" → {"sub_intent": "schedule", "team": "BYU", "sport": "football"}
"How did BYU do last year?" → {"sub_intent": "historical", "team": "BYU", "sport": ""}
"What's the Big 12 standings?" → {"sub_intent": "standings", "team": "", "sport": "basketball"}
"Is there a game on right now?" → {"sub_intent": "live_scores", "team": "", "sport": ""}
"Who won the Super Bowl?" → {"sub_intent": "historical", "team": "", "sport": "nfl"}
"What's BYU's record?" → {"sub_intent": "standings", "team": "BYU", "sport": ""}"""


async def classify_sports_intent(message: str) -> dict[str, str]:
    """Use Cerebras to classify a sports query into sub-intent + entities.

    Returns: {"sub_intent": str, "team": str, "sport": str}
    Falls back to {"sub_intent": "general", "team": "", "sport": ""} on failure.
    """
    client = _get_client()
    fallback = {"sub_intent": "general", "team": "", "sport": ""}

    if not client:
        logger.debug("Cerebras not configured — sports intent defaults to general")
        return fallback

    import json as _json

    models = ["qwen-3-235b-a22b-instruct-2507", "gpt-oss-120b"]

    for model in models:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SPORTS_ROUTER_PROMPT},
                    {"role": "user", "content": message},
                ],
                max_tokens=100,
                temperature=0,
            )

            raw = response.choices[0].message.content.strip()

            # Handle <think>...</think> tags from reasoning models
            if "<think>" in raw:
                think_end = raw.rfind("</think>")
                if think_end != -1:
                    raw = raw[think_end + 8:].strip()

            # Extract JSON from response (might have markdown fences)
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            result = _json.loads(raw)
            # Validate required fields
            sub_intent = result.get("sub_intent", "general")
            valid_intents = {"live_scores", "recent_result", "schedule", "standings", "historical", "general"}
            if sub_intent not in valid_intents:
                sub_intent = "general"

            classified = {
                "sub_intent": sub_intent,
                "team": result.get("team", ""),
                "sport": result.get("sport", ""),
            }
            logger.info("Sports sub-intent: %s (team=%s, sport=%s)", classified["sub_intent"], classified["team"], classified["sport"])
            return classified

        except Exception as exc:
            logger.warning("Cerebras sports classification (%s) failed: %s", model, exc)
            continue

    logger.warning("All Cerebras models failed for sports classification — defaulting to general")
    return fallback
