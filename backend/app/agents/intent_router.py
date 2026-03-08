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
        "description": "Directions, maps, travel time, places, location",
        "tools": ["google_maps", "mac_maps_search", "mac_maps_directions", "mac_maps_eta", "mac_location_current", "mac_location_geocode"],
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
        "description": "iMessage, SMS, text messages (READ ONLY)",
        "tools": ["mac_messages_fetch"],
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
