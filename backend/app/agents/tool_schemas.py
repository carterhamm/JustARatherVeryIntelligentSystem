"""
Anthropic tool definitions for J.A.R.V.I.S. tools.

Maps each tool in the registry to a Claude-compatible tool definition
with proper JSON schemas for input validation.
"""

from __future__ import annotations

from typing import Any


def get_anthropic_tools() -> list[dict[str, Any]]:
    """Return all JARVIS tools as Anthropic tool definitions.

    Each tool has: name, description, input_schema (JSON Schema).
    These are passed to the Claude Messages API ``tools`` parameter.
    """
    return [t for t in _TOOL_DEFINITIONS if t is not None]


def get_anthropic_tools_by_name(names: list[str]) -> list[dict[str, Any]]:
    """Return a subset of tool definitions filtered by name."""
    name_set = set(names)
    return [t for t in _TOOL_DEFINITIONS if t["name"] in name_set]


# ═══════════════════════════════════════════════════════════════════════════
# Tool definitions
# ═══════════════════════════════════════════════════════════════════════════

_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # -- Knowledge --------------------------------------------------------
    {
        "name": "search_knowledge",
        "description": (
            "Search the user's personal knowledge base (documents, notes, "
            "emails, messages) using semantic search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "limit": {
                    "type": "integer",
                    "description": "Max results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    # -- Email ------------------------------------------------------------
    {
        "name": "send_email",
        "description": "Send an email using the user's Gmail account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Email body text."},
                "cc": {"type": "string", "description": "CC recipient(s)."},
                "bcc": {"type": "string", "description": "BCC recipient(s)."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "read_email",
        "description": "Read recent emails from the user's Gmail inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (e.g. 'from:john', 'is:unread').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max emails to return.",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
    # -- Calendar ---------------------------------------------------------
    {
        "name": "create_calendar_event",
        "description": "Create a new event on Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title."},
                "start": {"type": "string", "description": "Start time in ISO 8601 format."},
                "end": {"type": "string", "description": "End time in ISO 8601 format."},
                "description": {"type": "string", "description": "Event description."},
                "location": {"type": "string", "description": "Event location."},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses.",
                },
            },
            "required": ["title", "start", "end"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "List upcoming calendar events within a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date in ISO format."},
                "end_date": {"type": "string", "description": "End date in ISO format."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    # -- Reminders --------------------------------------------------------
    {
        "name": "set_reminder",
        "description": "Set a reminder that will notify the user at the specified time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Reminder message."},
                "remind_at": {"type": "string", "description": "When to remind, in ISO 8601 format."},
            },
            "required": ["message", "remind_at"],
        },
    },
    # -- Smart Home -------------------------------------------------------
    {
        "name": "smart_home_control",
        "description": (
            "Control smart home devices via Matter protocol. "
            "Supports lights, switches, thermostats, locks, and sensors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "on", "off", "brightness", "temperature", "lock", "unlock", "status"],
                    "description": "Action to perform.",
                },
                "device_id": {"type": "string", "description": "Target device ID (not needed for 'list')."},
                "value": {"type": "string", "description": "Value for brightness (0-100) or temperature."},
            },
            "required": ["action"],
        },
    },
    # -- Web Search -------------------------------------------------------
    {
        "name": "web_search",
        "description": "Search the web for current information using Tavily, SerpAPI, or Brave.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "limit": {
                    "type": "integer",
                    "description": "Max results.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    # -- Weather ----------------------------------------------------------
    {
        "name": "weather",
        "description": (
            "Get current weather and forecasts for a location using OpenWeatherMap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name or 'lat,lon' coordinates."},
                "type": {
                    "type": "string",
                    "enum": ["current", "forecast"],
                    "description": "Weather data type.",
                    "default": "current",
                },
            },
            "required": ["location"],
        },
    },
    # -- News -------------------------------------------------------------
    {
        "name": "news",
        "description": "Get latest news headlines or search news articles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (optional for top headlines)."},
                "category": {
                    "type": "string",
                    "enum": ["business", "entertainment", "general", "health", "science", "sports", "technology"],
                    "description": "News category for top headlines.",
                },
                "limit": {"type": "integer", "description": "Max articles.", "default": 5},
            },
            "required": [],
        },
    },
    # -- Spotify ----------------------------------------------------------
    {
        "name": "spotify",
        "description": (
            "Control Spotify playback and search for music. "
            "Actions: play, pause, next, previous, search, current, volume, queue."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "next", "previous", "search", "current", "volume", "queue"],
                    "description": "Spotify action to perform.",
                },
                "query": {"type": "string", "description": "Search query (for 'search' action)."},
                "uri": {"type": "string", "description": "Spotify URI to play (for 'play' action)."},
                "volume": {"type": "integer", "description": "Volume level 0-100 (for 'volume' action)."},
            },
            "required": ["action"],
        },
    },
    # -- Calculator -------------------------------------------------------
    {
        "name": "calculator",
        "description": "Evaluate mathematical expressions safely. Supports basic arithmetic, trig, log, sqrt, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Mathematical expression to evaluate."},
            },
            "required": ["expression"],
        },
    },
    # -- Date/Time --------------------------------------------------------
    {
        "name": "date_time",
        "description": (
            "Get current date/time, convert between timezones, or calculate date differences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["now", "convert", "difference"],
                    "description": "Action: 'now' for current time, 'convert' for timezone conversion, 'difference' for date diff.",
                },
                "timezone": {"type": "string", "description": "Timezone name (e.g. 'America/New_York')."},
                "from_time": {"type": "string", "description": "Source datetime for conversion (ISO format)."},
                "to_timezone": {"type": "string", "description": "Target timezone for conversion."},
                "date1": {"type": "string", "description": "First date for difference calculation."},
                "date2": {"type": "string", "description": "Second date for difference calculation."},
            },
            "required": ["action"],
        },
    },
    # -- iMCP (macOS native) tools ----------------------------------------
    {
        "name": "mac_calendars_list",
        "description": "List all available calendars on the user's Mac.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mac_events_fetch",
        "description": "Fetch calendar events from the user's Mac within a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (ISO format)."},
                "end_date": {"type": "string", "description": "End date (ISO format)."},
                "calendar_name": {"type": "string", "description": "Specific calendar name to filter."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "mac_events_create",
        "description": "Create a new calendar event on the user's Mac.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title."},
                "start_date": {"type": "string", "description": "Start datetime (ISO format)."},
                "end_date": {"type": "string", "description": "End datetime (ISO format)."},
                "calendar_name": {"type": "string", "description": "Which calendar to add to."},
                "notes": {"type": "string", "description": "Event notes."},
                "location": {"type": "string", "description": "Event location."},
            },
            "required": ["title", "start_date", "end_date"],
        },
    },
    {
        "name": "mac_contacts_me",
        "description": "Get the user's own contact information from their Mac.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mac_contacts_search",
        "description": "Search contacts on the user's Mac by name, email, or phone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (name, email, or phone)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "mac_contacts_create",
        "description": "Create a new contact on the user's Mac.",
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "description": "First name."},
                "last_name": {"type": "string", "description": "Last name."},
                "email": {"type": "string", "description": "Email address."},
                "phone": {"type": "string", "description": "Phone number."},
            },
            "required": ["first_name"],
        },
    },
    {
        "name": "mac_messages_fetch",
        "description": "Fetch recent iMessages/SMS from the user's Mac.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact": {"type": "string", "description": "Filter by contact name or number."},
                "limit": {"type": "integer", "description": "Max messages to return.", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "mac_reminders_lists",
        "description": "List all reminder lists on the user's Mac.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mac_reminders_fetch",
        "description": "Fetch reminders from the user's Mac.",
        "input_schema": {
            "type": "object",
            "properties": {
                "list_name": {"type": "string", "description": "Specific reminder list to fetch from."},
                "include_completed": {"type": "boolean", "description": "Include completed reminders.", "default": False},
            },
            "required": [],
        },
    },
    {
        "name": "mac_reminders_create",
        "description": "Create a new reminder on the user's Mac.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Reminder title."},
                "list_name": {"type": "string", "description": "Which reminder list to add to."},
                "due_date": {"type": "string", "description": "Due date (ISO format)."},
                "notes": {"type": "string", "description": "Reminder notes."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "mac_location_current",
        "description": "Get the user's current location from their Mac.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "mac_location_geocode",
        "description": "Geocode an address to coordinates, or reverse geocode coordinates to an address.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Address to geocode."},
                "latitude": {"type": "number", "description": "Latitude for reverse geocoding."},
                "longitude": {"type": "number", "description": "Longitude for reverse geocoding."},
            },
            "required": [],
        },
    },
    {
        "name": "mac_maps_search",
        "description": "Search for places/businesses on Apple Maps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g. 'coffee shops near me')."},
                "limit": {"type": "integer", "description": "Max results.", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "mac_maps_directions",
        "description": "Get directions between two locations via Apple Maps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_address": {"type": "string", "description": "Starting address."},
                "to_address": {"type": "string", "description": "Destination address."},
                "transport_type": {
                    "type": "string",
                    "enum": ["driving", "walking", "transit"],
                    "description": "Mode of transport.",
                    "default": "driving",
                },
            },
            "required": ["from_address", "to_address"],
        },
    },
    {
        "name": "mac_maps_eta",
        "description": "Get estimated travel time between two locations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_address": {"type": "string", "description": "Starting address."},
                "to_address": {"type": "string", "description": "Destination address."},
                "transport_type": {
                    "type": "string",
                    "enum": ["driving", "walking", "transit"],
                    "default": "driving",
                },
            },
            "required": ["from_address", "to_address"],
        },
    },
    {
        "name": "mac_weather_current",
        "description": "Get current weather conditions from the user's Mac (Apple Weather).",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Location (defaults to current location if omitted)."},
            },
            "required": [],
        },
    },
    {
        "name": "mac_weather_forecast",
        "description": "Get weather forecast from the user's Mac (Apple Weather).",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Location (defaults to current location if omitted)."},
                "days": {"type": "integer", "description": "Number of forecast days.", "default": 5},
            },
            "required": [],
        },
    },
    # -- Google Drive -----------------------------------------------------
    {
        "name": "google_drive",
        "description": (
            "Interact with Google Drive: list, search, read, or upload files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "search", "read", "upload"],
                    "description": "Drive action to perform.",
                },
                "query": {"type": "string", "description": "Search query (for 'search' action)."},
                "file_id": {"type": "string", "description": "File ID (for 'read' action)."},
                "folder_id": {"type": "string", "description": "Folder ID (for 'list' action)."},
                "limit": {"type": "integer", "description": "Max results.", "default": 10},
            },
            "required": ["action"],
        },
    },
    # -- Slack ------------------------------------------------------------
    {
        "name": "slack",
        "description": (
            "Interact with Slack: send messages, read channels, list channels."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send", "read", "list_channels", "search"],
                    "description": "Slack action to perform.",
                },
                "channel": {"type": "string", "description": "Channel name or ID."},
                "message": {"type": "string", "description": "Message text (for 'send' action)."},
                "query": {"type": "string", "description": "Search query (for 'search' action)."},
                "limit": {"type": "integer", "description": "Max messages/results.", "default": 10},
            },
            "required": ["action"],
        },
    },
    # -- GitHub -----------------------------------------------------------
    {
        "name": "github",
        "description": (
            "Interact with GitHub: list repos, issues, PRs, create issues, search code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_repos", "list_issues", "list_prs", "create_issue", "search_code", "repo_info"],
                    "description": "GitHub action to perform.",
                },
                "repo": {"type": "string", "description": "Repository in 'owner/repo' format."},
                "title": {"type": "string", "description": "Issue/PR title."},
                "body": {"type": "string", "description": "Issue/PR body."},
                "query": {"type": "string", "description": "Search query."},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "default": "open",
                },
                "limit": {"type": "integer", "description": "Max results.", "default": 10},
            },
            "required": ["action"],
        },
    },
    # -- Wolfram Alpha ----------------------------------------------------
    {
        "name": "wolfram_alpha",
        "description": "Query Wolfram Alpha for computational knowledge, math, science, data analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query to send to Wolfram Alpha."},
            },
            "required": ["query"],
        },
    },
    # -- Perplexity Research ----------------------------------------------
    {
        "name": "perplexity_research",
        "description": "Research a topic in depth using Perplexity AI with web access and citations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research query."},
            },
            "required": ["query"],
        },
    },
    # -- Financial Data ---------------------------------------------------
    {
        "name": "financial_data",
        "description": "Get stock quotes, company financials, forex rates, and crypto prices via Alpha Vantage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["quote", "company", "forex", "crypto", "search"],
                    "description": "Financial data action.",
                },
                "symbol": {"type": "string", "description": "Stock/crypto ticker symbol."},
                "from_currency": {"type": "string", "description": "Source currency (for forex)."},
                "to_currency": {"type": "string", "description": "Target currency (for forex)."},
                "query": {"type": "string", "description": "Search query (for 'search' action)."},
            },
            "required": ["action"],
        },
    },
    # -- Flight Tracker ---------------------------------------------------
    {
        "name": "flight_tracker",
        "description": "Track flights, check status, and search routes via AviationStack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "search", "arrivals", "departures"],
                    "description": "Flight tracker action.",
                },
                "flight_number": {"type": "string", "description": "Flight number (e.g. 'AA100')."},
                "airport": {"type": "string", "description": "Airport IATA code (e.g. 'LAX')."},
                "date": {"type": "string", "description": "Date in ISO format."},
                "limit": {"type": "integer", "description": "Max results.", "default": 5},
            },
            "required": ["action"],
        },
    },
    # -- Google Maps ------------------------------------------------------
    {
        "name": "google_maps",
        "description": "Search places, get directions, geocode addresses, find nearby places via Google Maps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "directions", "geocode", "nearby", "place_details"],
                    "description": "Maps action to perform.",
                },
                "query": {"type": "string", "description": "Search query or address."},
                "origin": {"type": "string", "description": "Starting point (for directions)."},
                "destination": {"type": "string", "description": "End point (for directions)."},
                "location": {"type": "string", "description": "Location for nearby search (lat,lng or address)."},
                "radius": {"type": "integer", "description": "Search radius in metres.", "default": 1000},
                "place_type": {"type": "string", "description": "Place type filter (e.g. 'restaurant')."},
                "place_id": {"type": "string", "description": "Google Place ID (for place_details)."},
                "mode": {
                    "type": "string",
                    "enum": ["driving", "walking", "bicycling", "transit"],
                    "default": "driving",
                },
            },
            "required": ["action"],
        },
    },
    # -- Nutrition & Recipes ----------------------------------------------
    {
        "name": "nutrition_recipe",
        "description": "Search recipes, get nutrition info, and meal planning via Edamam.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_recipes", "nutrition", "meal_plan"],
                    "description": "Nutrition action.",
                },
                "query": {"type": "string", "description": "Search query or food item."},
                "diet": {"type": "string", "description": "Diet filter (e.g. 'low-carb', 'high-protein')."},
                "health": {"type": "string", "description": "Health filter (e.g. 'gluten-free', 'vegan')."},
                "limit": {"type": "integer", "description": "Max results.", "default": 5},
            },
            "required": ["action"],
        },
    },
]
