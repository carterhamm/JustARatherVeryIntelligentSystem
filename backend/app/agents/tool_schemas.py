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

    Excludes iMCP (mac_*) tools when running on Railway (no macOS).
    """
    import os
    on_railway = bool(os.environ.get("RAILWAY_SERVICE_ID"))
    return [
        t for t in _TOOL_DEFINITIONS
        if t is not None and (not on_railway or not t["name"].startswith("mac_"))
    ]


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
    {
        "name": "read_icloud_email",
        "description": (
            "Read recent emails from the user's iCloud Mail inbox via IMAP. "
            "Use when the user asks about iCloud email specifically, or when "
            "Gmail is not connected but iCloud is."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Search query. Supports 'from:name', 'subject:text', "
                        "'unread', or freeform text to search both sender and subject."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max emails to return.",
                    "default": 5,
                },
                "days": {
                    "type": "integer",
                    "description": "How many days back to search (only used when no query).",
                    "default": 7,
                },
            },
            "required": [],
        },
    },
    {
        "name": "send_jarvis_email",
        "description": (
            "Send an email FROM jarvis@malibupoint.dev (JARVIS's own email address). "
            "Use for JARVIS-initiated emails: daily briefings, alerts, reports sent TO the owner. "
            "NEVER impersonate the owner."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Plain text email body."},
                "html": {"type": "string", "description": "Optional HTML email body."},
            },
            "required": ["to", "subject", "body"],
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
    # -- Morning Routine ------------------------------------------------
    {
        "name": "set_wake_time",
        "description": "Set or change Mr. Stark's morning routine wake time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "time": {"type": "string", "description": "Wake time in HH:MM format (e.g. '07:00', '6:45')."},
            },
            "required": ["time"],
        },
    },
    # -- Send iMessage (via Mac Mini) -----------------------------------
    {
        "name": "send_imessage",
        "description": (
            "Send an iMessage to a phone number or Apple ID via the Mac Mini. "
            "This sends FROM JARVIS's Mac Mini — never from the user's device. "
            "Use for sending links, alerts, or notifications to Mr. Stark or others."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number (E.164 format like '+15551234567') or Apple ID email.",
                },
                "text": {
                    "type": "string",
                    "description": "Message text to send.",
                },
            },
            "required": ["to", "text"],
        },
    },
    # -- Sports (Cerebras-routed: ESPN + Gemini web search) ----------------
    {
        "name": "sports",
        "description": (
            "Answer any sports question. Just pass the user's question as 'query'. "
            "The tool automatically classifies the intent and fetches real data "
            "from ESPN or web search. Do NOT try to answer sports questions yourself — "
            "ALWAYS use this tool and relay its response verbatim."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's sports question in natural language. Pass it exactly as they asked it.",
                },
            },
            "required": ["query"],
        },
    },
    # -- Scripture Lookup -----------------------------------------------
    {
        "name": "scripture_lookup",
        "description": (
            "Look up scripture verses from the Bible (KJV) or LDS scriptures "
            "(Book of Mormon, Doctrine & Covenants, Pearl of Great Price). "
            "Supports references like 'John 3:16', '1 Nephi 3:7', 'Alma 32:21', 'D&C 121:7-8'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference": {
                    "type": "string",
                    "description": "Scripture reference (e.g. 'John 3:16', '1 Nephi 3:7', 'D&C 121:7-8', 'Mosiah 2:17').",
                },
            },
            "required": ["reference"],
        },
    },
    # -- Navigate (Find My + Google Maps) --------------------------------
    {
        "name": "navigate",
        "description": (
            "Get driving distance and estimated travel time from Mr. Stark's "
            "current location to a destination. Automatically gets live location "
            "from Find My on the Mac Mini, then calculates route via Google Maps. "
            "Also shows nearby place matches for disambiguation (e.g. 'La Jolla' "
            "could be a restaurant nearby or the city in California)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "Where to navigate to (place name, address, or city).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["driving", "walking", "transit", "bicycling"],
                    "description": "Travel mode.",
                    "default": "driving",
                },
            },
            "required": ["destination"],
        },
    },
    # -- Mac Mini Remote Exec -------------------------------------------
    {
        "name": "mac_mini_exec",
        "description": (
            "Run a shell command on the Mac Mini remotely. Full SSH-like access. "
            "Use for system admin, checking logs, installing packages, running scripts, "
            "managing files, or any shell task on the Mini."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (e.g. 'ls -la', 'brew update', 'cat /var/log/system.log').",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory (defaults to home).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait.",
                    "default": 120,
                },
            },
            "required": ["command"],
        },
    },
    # -- Mac Mini Claude Code -------------------------------------------
    {
        "name": "mac_mini_claude_code",
        "description": (
            "Run Claude Code on the Mac Mini with full autonomous permissions. "
            "Use for complex multi-step development tasks, system configuration, "
            "debugging, or any task that benefits from Claude Code's capabilities "
            "running directly on the Mini."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task/prompt for Claude Code to execute.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for Claude Code.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds (default 600 = 10 min).",
                    "default": 600,
                },
                "model": {
                    "type": "string",
                    "description": "Model override (empty = default).",
                },
            },
            "required": ["prompt"],
        },
    },
    # -- Mac Mini Screenshot --------------------------------------------
    {
        "name": "mac_mini_screenshot",
        "description": (
            "Capture a screenshot of the Mac Mini's screen. Returns the image "
            "as base64 PNG. Use to see what's currently displayed on the Mini."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thumbnail": {
                    "type": "boolean",
                    "description": "Return smaller image (1024px wide). Default true.",
                    "default": True,
                },
            },
            "required": [],
        },
    },
    # -- Search Contacts -------------------------------------------------
    {
        "name": "search_contacts",
        "description": (
            "Search the user's uploaded contacts by name, phone number, email, "
            "company, or any other field. Use when the user asks for someone's "
            "number, email, or other contact info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (name, phone, email, company, etc.).",
                },
            },
            "required": ["query"],
        },
    },
    # -- Health Summary ---------------------------------------------------
    {
        "name": "health_summary",
        "description": (
            "Get the user's health data summary from Apple HealthKit (synced via iOS app). "
            "Returns today's steps, latest heart rate, last night's sleep, and recent workouts. "
            "Use when the user asks about their health, fitness, steps, sleep, heart rate, or workouts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # -- System Health ---------------------------------------------------
    {
        "name": "system_health",
        "description": (
            "Check real-time health of all JARVIS infrastructure: Railway backend, "
            "Mac Mini agent, LM Studio, XTTS voice, Qdrant, Redis, PostgreSQL, "
            "ElevenLabs, and Gemini. Use when asked 'are all systems running?' "
            "or any system status question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "force_refresh": {
                    "type": "boolean",
                    "description": "Bypass the 5-minute cache and probe all systems live.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    # -- MCP Discovery ---------------------------------------------------
    {
        "name": "mcp_discovery",
        "description": (
            "Search GitHub for MCP servers that could give JARVIS new capabilities. "
            "Can search by keyword, deep-evaluate a specific repo, recommend integrations "
            "based on current capability gaps, or list what's already installed. "
            "Use when the user asks about new integrations, plugins, skills, or MCP servers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "evaluate", "recommend", "scan", "installed"],
                    "description": (
                        "Action to perform: 'search' finds servers matching a query, "
                        "'evaluate' deep-evaluates a specific repo URL, "
                        "'recommend' suggests MCPs based on JARVIS's capability gaps, "
                        "'scan' runs a full background scan (takes ~1 min), "
                        "'installed' lists JARVIS's current tools."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "For 'search': keyword to search (e.g. 'slack', 'notion', 'browser'). "
                        "For 'evaluate': GitHub repo URL (e.g. 'https://github.com/owner/repo'). "
                        "Not required for 'recommend', 'scan', or 'installed'."
                    ),
                },
            },
            "required": ["action"],
        },
    },
    # -- Focus Session ---------------------------------------------------
    {
        "name": "focus_session",
        "description": (
            "Manage deep work and focused learning sessions. "
            "Start a session ('start a 90 min physics study session'), "
            "end it with ratings ('end my session, productivity 4/5'), "
            "check status ('am I in a focus session?'), "
            "or get stats ('how much deep work did I do this week?')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "end", "status", "stats"],
                    "description": "Action to perform.",
                },
                "title": {
                    "type": "string",
                    "description": "Session title, e.g. 'Physics - Quantum Mechanics' (required for start).",
                },
                "category": {
                    "type": "string",
                    "enum": ["learning", "deep_work", "creative", "admin"],
                    "description": "Session category.",
                },
                "planned_duration_min": {
                    "type": "integer",
                    "description": "Target duration in minutes (for start).",
                },
                "notes": {
                    "type": "string",
                    "description": "Session notes or reflections (for end).",
                },
                "energy_level": {
                    "type": "integer",
                    "description": "Energy level rating 1-5 (for end).",
                },
                "productivity_rating": {
                    "type": "integer",
                    "description": "Productivity rating 1-5 (for end).",
                },
                "distractions": {
                    "type": "integer",
                    "description": "Number of distractions (for end, overrides auto-count).",
                },
                "period": {
                    "type": "string",
                    "enum": ["week", "month"],
                    "description": "Stats time period (for stats action, default 'week').",
                    "default": "week",
                },
            },
            "required": ["action"],
        },
    },
    # -- Habit Tracker ---------------------------------------------------
    {
        "name": "habit_tracker",
        "description": (
            "Track and manage habits. Actions: 'list' shows all active habits with today's "
            "status and streaks; 'log' marks a habit as completed; 'streak' checks streak info. "
            "Use when the user mentions habits, streaks, tracking, or daily routines."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "log", "streak", "create"],
                    "description": (
                        "'list' = show all habits and today's progress; "
                        "'log' = mark a habit complete; "
                        "'streak' = check streak for a specific habit; "
                        "'create' = create a new habit."
                    ),
                },
                "habit_name": {
                    "type": "string",
                    "description": "Name of the habit (for 'log', 'streak', 'create' actions). Fuzzy-matched against existing habits.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for the completion log.",
                },
                "frequency": {
                    "type": "string",
                    "enum": ["daily", "weekday", "weekly", "custom"],
                    "description": "Frequency for new habits (default: 'daily').",
                },
            },
            "required": ["action"],
        },
    },
    # -- Camera / Vision --------------------------------------------------
    {
        "name": "camera_look",
        "description": (
            "Look through the security camera. Can capture a snapshot and describe "
            "what you see, or control the camera's pan/tilt/zoom. Use when the user "
            "asks you to look at something, check the camera, or control PTZ."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["look", "ptz"],
                    "description": (
                        "'look' = capture and analyze a frame. "
                        "'ptz' = move the camera (requires direction param)."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "What to look for or describe (for 'look' action).",
                },
                "direction": {
                    "type": "string",
                    "enum": ["left", "right", "up", "down", "home", "zoom_in", "zoom_out"],
                    "description": "PTZ direction (for 'ptz' action).",
                },
            },
            "required": ["action"],
        },
    },
    # -- Research Briefing -----------------------------------------------
    {
        "name": "research_briefing",
        "description": (
            "Retrieve JARVIS's own research findings from the continuous learning daemon. "
            "Topics: business_ideas, tech_industry, apple_tech, iron_man_tech, "
            "graphene_nanotech, physics, ai_ml, cybersecurity, space_tech. "
            "Use when the user asks what JARVIS has been learning or wants a research update."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": (
                        "Filter to a specific topic (e.g. 'ai_ml', 'physics'). "
                        "Omit or leave empty for all topics."
                    ),
                },
                "days": {
                    "type": "integer",
                    "description": "How many days back to include findings.",
                    "default": 3,
                },
            },
            "required": [],
        },
    },
    # -- List Reminders -----------------------------------------------------
    {
        "name": "list_reminders",
        "description": (
            "List upcoming reminders from the JARVIS database. Use to find existing "
            "reminders before rescheduling or updating them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_delivered": {
                    "type": "boolean",
                    "description": "Include already-delivered reminders.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max reminders to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    # -- Update Reminder ---------------------------------------------------
    {
        "name": "update_reminder",
        "description": (
            "Update or reschedule an existing reminder. Can change time, message, "
            "or cancel it. Must provide reminder_id (get from list_reminders first)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {
                    "type": "string",
                    "description": "UUID of the reminder to update.",
                },
                "remind_at": {
                    "type": "string",
                    "description": "New datetime in ISO format (e.g. 2026-03-17T15:30:00-06:00).",
                },
                "message": {
                    "type": "string",
                    "description": "New message text for the reminder.",
                },
                "cancel": {
                    "type": "boolean",
                    "description": "If true, mark the reminder as done/cancelled.",
                },
            },
            "required": ["reminder_id"],
        },
    },
    # -- Autonomy Status ---------------------------------------------------
    {
        "name": "autonomy_status",
        "description": (
            "Check JARVIS's autonomous systems status: self-awareness model, "
            "code health, proactive features, and self-improvement metrics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # -- Learning Status ---------------------------------------------------
    {
        "name": "learning_status",
        "description": (
            "Check JARVIS's continuous learning status and knowledge growth. "
            "Reports documents ingested, entities discovered, dialogue sessions, "
            "and knowledge base size. Use when asked about JARVIS's learning progress."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # -- Self-Healing / Auto-Repair ----------------------------------------
    {
        "name": "self_heal",
        "description": (
            "Diagnose and attempt to automatically fix integration issues. "
            "Use when a tool or service fails. Can refresh OAuth tokens, "
            "restart connections, and escalate to Claude Code on the Mac Mini "
            "for complex fixes that JARVIS cannot resolve alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {
                    "type": "string",
                    "description": "Description of the problem to diagnose/fix.",
                },
                "service": {
                    "type": "string",
                    "description": "Which service is failing: google, calendar, gmail, imessage, redis, etc.",
                },
                "escalate": {
                    "type": "boolean",
                    "description": "If true, invoke Claude Code on Mac Mini to attempt a code-level fix.",
                    "default": False,
                },
            },
            "required": ["issue", "service"],
        },
    },
]
