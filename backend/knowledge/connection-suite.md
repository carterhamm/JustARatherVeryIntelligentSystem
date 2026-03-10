# J.A.R.V.I.S. Connection Suite — Integration Reference

Last updated: 2026-03-09

## Current State Summary

**31 tools** registered in `tools.py`, with **17 iMCP tools** (macOS native), **14 API-backed tools**, plus supporting infrastructure (Twilio phone calls, TTS, vision, whisper STT).

---

## TIER 1 — Built and Functional (need API keys or minor config)

These tools exist in `tools.py` with full implementations in `integrations/`. They work today if the API key is set in Railway env vars.

| Tool | Integration File | Config Var | Status |
|------|-----------------|------------|--------|
| `search_knowledge` | Local keyword search + Qdrant | QDRANT_URL, QDRANT_API_KEY | Working (local fallback always works) |
| `send_email` / `read_email` | `gmail.py` | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN | Working if Google OAuth configured |
| `send_jarvis_email` | `resend_email.py` | RESEND_API_KEY | Working — sends from jarvis@malibupoint.dev |
| `create_calendar_event` / `list_calendar_events` | `calendar.py` | Same Google OAuth | Working if Google OAuth configured |
| `set_reminder` | DB model `Reminder` | DATABASE_URL | Working — persists to PostgreSQL |
| `web_search` | `web_search.py` | TAVILY_API_KEY or SERPAPI_API_KEY or BRAVE_SEARCH_API_KEY | Working — falls back to Gemini grounded search |
| `weather` | `weather.py` | WEATHER_API_KEY (OpenWeatherMap) | Working |
| `news` | `news.py` | NEWS_API_KEY | Working |
| `spotify` | `spotify.py` | SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN | Working if Spotify OAuth configured |
| `calculator` | Inline (safe eval) | None needed | Working |
| `date_time` | Inline (zoneinfo) | None needed | Working |
| `google_drive` | `google_drive.py` | Same Google OAuth + GOOGLE_DRIVE_ENABLED=true | Working if enabled |
| `slack` | `slack_client.py` | SLACK_BOT_TOKEN + SLACK_ENABLED=true | Working if Slack app configured |
| `github` | `github_client.py` | GITHUB_TOKEN + GITHUB_ENABLED=true | Working if token set |
| `wolfram_alpha` | `wolfram.py` | WOLFRAM_APP_ID | Working if key set |
| `perplexity_research` | `perplexity.py` | PERPLEXITY_API_KEY | Working if key set |
| `financial_data` | `alpha_vantage.py` | ALPHA_VANTAGE_API_KEY | Working if key set |
| `flight_tracker` | `flight_tracker.py` | AVIATIONSTACK_API_KEY | Working if key set |
| `google_maps` | `google_maps.py` | GOOGLE_MAPS_API_KEY | Working if key set |
| `nutrition_recipe` | `edamam.py` | EDAMAM_APP_ID, EDAMAM_APP_KEY | Working if keys set |
| `set_wake_time` | Redis store | REDIS_URL | Working |
| 17 `mac_*` tools | `mcp_client.py` via iMCP bridge | IMCP_BRIDGE_URL, IMCP_BRIDGE_KEY | Working when MacBook iMCP bridge is running |

### Tier 1 supporting infrastructure (not tools, but built):
- **Twilio voice calls**: Full implementation in `twilio_client.py` + `twilio_routes.py`. Incoming calls, outgoing calls, STT via Twilio, TTS via ElevenLabs. Needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, TWILIO_USER_PHONE.
- **ElevenLabs TTS**: `elevenlabs.py` — used for phone calls and morning routine.
- **JARVIS TTS (XTTS-v2)**: `jarvis_tts.py` — local Unix socket or remote via JARVIS_VOICE_URL. Running on Mac Mini.
- **Vision (GPT-4o)**: `vision.py` — image analysis, OCR, object detection. Needs OpenAI key (not in config.py — uses direct AsyncOpenAI).
- **Whisper STT**: `whisper.py` — audio transcription. Needs OpenAI key.
- **Morning routine cron**: `cron.py` — gathers weather/calendar/news, generates briefing script, plays via ElevenLabs + iMCP bridge.

### Tier 1 TODO (just enable / set keys):
1. **Verify all API keys are set on Railway** — some may be placeholder values.
2. **Google OAuth refresh token** — confirm it's not expired. Google refresh tokens last indefinitely if the app stays verified.
3. **Spotify refresh token** — these expire if the Spotify app is in development mode and unused for 90 days.
4. **Vision/Whisper** — need OpenAI API key added to config.py (currently hardcoded in class constructors, not in Settings).

---

## TIER 2 — Can Build Now with Existing APIs

These are new integrations that use well-documented public APIs and can be added as new tool classes in `tools.py` + integration modules in `integrations/`.

### 2A. Google Sheets (via existing Google OAuth)
- **What**: Read/write/create spreadsheets. Use for budget tracking, habit logging, data storage.
- **API**: `google-api-python-client` (already a dependency for Gmail/Calendar/Drive).
- **How**: New `GoogleSheetsClient` in `integrations/google_sheets.py`, new `google_sheets` tool in `tools.py`. Uses the same GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN.
- **Effort**: ~2 hours. Copy the pattern from `google_drive.py`.
- **Config**: Add GOOGLE_SHEETS_ENABLED to Settings.

### 2B. Sports — BYU Football / General Sports
- **What**: Game schedules, scores, standings for BYU Cougars and other teams.
- **API options**:
  - ESPN API (unofficial but stable): `https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=4` — free, no key needed.
  - SportsData.io: Free tier gives 1000 calls/month.
  - The-Odds-API: For betting lines (free tier).
- **How**: New `SportsClient` in `integrations/sports.py`, new `sports` tool. ESPN API is free and requires no key.
- **Effort**: ~2 hours.
- **Config**: Optional SPORTSDATA_API_KEY for premium data.

### 2C. LDS Scriptures / Gospel Library
- **What**: Search scriptures, get verse text, cross-references.
- **API options**:
  - Church of Jesus Christ API: `https://www.churchofjesuschrist.org/study/api/` — publicly accessible, no key.
  - Scripture API: `https://scripture.api.bible/` — free with key.
  - Local: Bundle scripture text as knowledge files in `backend/knowledge/` for SearchKnowledgeTool to find.
- **How**: New `ScriptureClient` in `integrations/scriptures.py`, new `scriptures` tool.
- **Effort**: ~3 hours. Parsing the Church API responses takes some work.
- **Config**: None required if using public Church API.

### 2D. Package Tracking
- **What**: Track USPS, UPS, FedEx, Amazon packages by tracking number.
- **API options**:
  - **17track API**: Free tier (100 queries/day). Supports all major carriers.
  - **AfterShip**: Free tier (50 trackings/month).
  - **USPS Web Tools**: Free, requires registration.
  - **Ship24**: Free tier (200 trackings/month).
- **How**: New `PackageTrackingClient` in `integrations/package_tracking.py`, new `track_package` tool.
- **Effort**: ~2 hours.
- **Config**: Add TRACKING_API_KEY (17track or AfterShip).

### 2E. Financial Improvements (Crypto, Portfolio)
- **What**: Extend existing `financial_data` tool with crypto prices, portfolio tracking.
- **API options**:
  - CoinGecko: Free tier (30 calls/min). Bitcoin, ETH, etc.
  - Alpha Vantage already supports crypto (action `crypto` is in the schema but implementation is partial).
- **How**: Extend `AlphaVantageClient` with crypto methods, or add `CoinGeckoClient`.
- **Effort**: ~1.5 hours.
- **Config**: Optional COINGECKO_API_KEY for higher rate limits.

### 2F. URL Summarizer / Web Page Reader
- **What**: Fetch a URL and summarize its content. Useful for links shared in conversation.
- **API**: Direct HTTP fetch + readability extraction (newspaper3k or trafilatura).
- **How**: New `url_summarize` tool. Fetch page, extract text, summarize with LLM.
- **Effort**: ~2 hours.
- **Config**: None.

### 2G. Translation
- **What**: Translate text between languages.
- **API options**:
  - Google Cloud Translation: Paid but cheap.
  - DeepL: Free tier (500k chars/month).
  - LLM-based: Just prompt Gemini/Claude to translate (zero API cost).
- **How**: New `translate` tool. LLM-based approach costs nothing and works well.
- **Effort**: ~1 hour.
- **Config**: Optional DEEPL_API_KEY.

### 2H. Timer / Stopwatch
- **What**: Set countdown timers, stopwatch functionality.
- **How**: Redis-backed timers. New `timer` tool that stores timer state in Redis and checks on query.
- **Effort**: ~1.5 hours.
- **Config**: None (uses existing Redis).

---

## TIER 3 — Needs Significant Architecture Work

### 3A. Habit Tracker
- **What**: Track daily habits (scripture reading, exercise, water, sleep, etc.) with streaks and stats.
- **Architecture needed**:
  - New DB model: `HabitDefinition` (name, frequency, target) and `HabitLog` (date, completed, value).
  - New tools: `habit_log`, `habit_status`, `habit_create`.
  - Cron job to check streaks and send morning reminders.
  - Optional: Google Sheets backing for data portability.
- **Effort**: ~6 hours (DB migration + tools + cron).
- **Config**: None beyond existing DB.

### 3B. Heartbeat / Notification System
- **What**: JARVIS proactively contacts user with reminders, alerts, daily briefings, weather warnings, calendar upcoming events.
- **Architecture needed**:
  - Background task runner (APScheduler or Railway cron jobs — Railway Pro supports cron).
  - Notification delivery: Email (Resend, already built), Phone call (Twilio, already built), Push notification (needs web push or APNs).
  - Reminder delivery worker: Query `Reminder` table for due reminders, deliver via preferred channel.
  - Event-triggered notifications: calendar event in 15 min, severe weather, package delivered.
- **Effort**: ~8 hours. The primitives exist (Resend email, Twilio calls), but the scheduler/dispatcher layer is missing.
- **Config**: Add NOTIFICATION_CHANNEL preference (email/call/push).
- **Key missing piece**: No background worker process. Options:
  1. Railway cron jobs (already used for morning routine) — add more cron endpoints.
  2. APScheduler in-process (runs inside the FastAPI process).
  3. Separate worker service on Railway.

### 3C. Conversation Memory / Learning (RAG Improvements)
- **What**: JARVIS remembers past conversations, learns user preferences over time, builds a user model.
- **Architecture needed**:
  - GraphRAG is partially built (`graphrag/` dir has entity_extractor, graph_store, hybrid_retriever, vector_store).
  - Neo4j graph store for entity relationships.
  - Qdrant vector store for semantic search.
  - What's missing: Automatic extraction pipeline — after each conversation, extract entities/facts and store them.
  - User preference learning: Track patterns (food preferences, schedule, contacts mentioned, etc.).
- **Effort**: ~12 hours. The framework exists but the pipeline connecting conversations to the knowledge graph is not wired up.
- **Config**: NEO4J_URI/USER/PASSWORD, QDRANT_URL/API_KEY (already in config).

### 3D. X/Twitter Integration
- **What**: Read timeline, search tweets, post tweets (with owner approval), track mentions.
- **API**: Twitter/X API v2. Free tier gives read-only (1500 tweets/month). Basic tier ($100/month) for posting.
- **Architecture needed**:
  - OAuth 2.0 flow for Twitter (separate from Google OAuth).
  - New `TwitterClient` in `integrations/twitter.py`.
  - HARD RULE enforcement: JARVIS must NEVER post as the user without explicit approval.
- **Effort**: ~5 hours.
- **Config**: TWITTER_BEARER_TOKEN, TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET.
- **Cost**: Free for read-only, $100/month for write access.

### 3E. Job Search Automation
- **What**: Search job listings, track applications, set alerts for new postings.
- **API options**:
  - LinkedIn API: Requires partner access (very restricted).
  - Indeed API: Deprecated.
  - Adzuna: Free tier (250 calls/day).
  - JSearch (via RapidAPI): Free tier.
  - Web scraping: fragile but works for specific sites.
- **Architecture needed**:
  - Job application DB model (company, role, status, date, notes).
  - Periodic scrape/search cron.
  - Alert system (ties into Tier 3B notification system).
- **Effort**: ~8 hours.
- **Config**: ADZUNA_APP_ID, ADZUNA_APP_KEY or RAPIDAPI_KEY.

### 3F. Computer Control (macOS)
- **What**: JARVIS controls the Mac — open apps, run shortcuts, control system settings, take screenshots.
- **Architecture needed**:
  - Extend iMCP bridge with new tools: `run_applescript`, `run_shortcut`, `open_app`, `screenshot`.
  - The iMCP bridge (`imcp_bridge.py`) already supports `run-shortcut` endpoint (used by morning routine).
  - New iMCP tools in tools.py.
  - Security: Rate limiting, allowlisted commands only.
- **Effort**: ~4 hours for basic control, ~10 hours for comprehensive control.
- **Config**: Uses existing IMCP_BRIDGE_URL/KEY.

### 3G. Autonomous Agent Loop
- **What**: JARVIS independently executes multi-step tasks: research a topic, compile a report, send it via email.
- **Architecture needed**:
  - Currently Claude's agentic_stream does up to 10 tool turns in a loop. This is the foundation.
  - Need: Task queue (Redis-backed), longer execution context, progress reporting via WebSocket.
  - Background task execution (not blocking the WebSocket connection).
  - Goal decomposition and planning layer.
- **Effort**: ~15 hours. Significant architecture work.
- **Config**: None beyond existing.

---

## TIER 4 — Future / Research Needed

### 4A. Live CCTV / Camera Integration
- **What**: View live camera feeds, motion detection alerts, record clips.
- **Options**: UniFi Protect API, RTSP streams, Frigate NVR.
- **Blockers**: Needs cameras installed. Heavy compute for video processing. Privacy concerns.
- **Effort**: ~20+ hours.

### 4B. Satellite Imagery
- **What**: View satellite images of locations, track weather patterns visually.
- **Options**: Mapbox Static Images API (free tier), Google Earth Engine (academic), Sentinel Hub.
- **Effort**: ~5 hours for static imagery, much more for analysis.

### 4C. OSINT (Open Source Intelligence)
- **What**: People search, company research, domain lookups, social media aggregation.
- **Options**: Hunter.io (email lookup), Clearbit (company data), Shodan (devices), BuiltWith (tech stacks).
- **Ethical/legal**: Must be careful about privacy. Only use for legitimate purposes.
- **Effort**: ~10 hours for a curated set of tools.

### 4D. Apple Health Integration
- **What**: Read health data (steps, heart rate, sleep, workouts) from Apple Health.
- **Blockers**: Apple Health data is only accessible on-device via HealthKit. No cloud API.
- **Options**:
  - Shortcuts + iMCP bridge: Create a Shortcut that reads Health data and sends it to JARVIS.
  - Auto-export app: Apps like "Health Auto Export" can push data to a webhook.
- **Effort**: ~6 hours with the Shortcuts approach.

### 4E. HomeKit / Smart Home (beyond Matter)
- **What**: Control HomeKit devices directly.
- **Options**:
  - HomeBridge API: If HomeBridge is running, it exposes a REST API.
  - Shortcuts + iMCP: Use Shortcuts to control HomeKit devices.
  - Matter (already in config): The Matter controller URL is configured but needs actual hardware.
- **Effort**: ~4 hours if using Shortcuts approach.
- **Config**: Already has MATTER_CONTROLLER_URL.

### 4F. Hotel / Flight Booking
- **What**: Search and book hotels, flights.
- **Options**: Amadeus API (free test tier), Skyscanner API (affiliate), Google Flights (no API).
- **Blockers**: Booking requires payment processing. Search-only is feasible.
- **Effort**: ~8 hours for search, booking is much more complex.

### 4G. Company/Business Automation
- **What**: CRM, invoicing, project management integration.
- **Options**: Notion API, Airtable API, Stripe API, QuickBooks API.
- **Effort**: Varies per integration, ~4-8 hours each.

---

## Priority Recommendation

### Quick Wins (do this week):
1. **Verify all Tier 1 API keys are live on Railway** — audit `.env` vs Railway env vars.
2. **Add OpenAI API key to config.py** — enables Vision and Whisper tools to be registered.
3. **Sports tool (ESPN)** — free, no key, ~2 hours. High user value (BYU football).
4. **Package tracking** — ~2 hours. Practical daily use.

### Next Sprint:
5. **Habit tracker** — DB model + tools. High personal value.
6. **Notification/heartbeat system** — leverage Railway cron + existing Resend/Twilio. Makes reminders actually fire.
7. **Google Sheets** — enables habit data export, budget tracking, structured data storage.
8. **LDS Scriptures** — personal importance, free API.

### Medium-term:
9. **Computer control via iMCP** — extend bridge, high utility.
10. **Conversation memory pipeline** — wire up GraphRAG extraction after each conversation.
11. **X/Twitter read-only** — social awareness.
12. **URL summarizer** — practical for daily use.

---

## File Reference

| Path | Purpose |
|------|---------|
| `backend/app/agents/tools.py` | All 31 tool implementations |
| `backend/app/agents/tool_schemas.py` | Anthropic tool definitions (JSON schemas) |
| `backend/app/config.py` | All env var settings |
| `backend/app/integrations/` | Integration client modules (33 files) |
| `backend/app/api/v1/cron.py` | Morning routine cron endpoint |
| `backend/app/api/v1/twilio_routes.py` | Phone call webhook endpoints |
| `backend/app/models/reminder.py` | Reminder DB model |
| `backend/app/graphrag/` | GraphRAG framework (entity extractor, graph store, hybrid retriever, vector store) |
| `backend/scripts/imcp_bridge.py` | iMCP HTTP bridge for remote macOS tools |
| `.env.example` | All supported env vars with placeholders |
