---
paths: "backend/**"
description: Python/FastAPI backend conventions for JARVIS
---

# Backend Rules (FastAPI/Python)

## Patterns
- All routes in `backend/app/api/v1/` — router prefix set in `__init__.py`, NOT in router files
- Dependencies in `backend/app/core/dependencies.py` — auth, DB sessions, Redis
- Services in `backend/app/services/` — business logic, separated from routes
- Integrations in `backend/app/integrations/` — external API wrappers
- Tools in `backend/app/agents/tools.py` — JARVIS agent tool implementations
- Tool schemas in `backend/app/agents/tool_schemas.py` — Gemini function declarations

## Auth Dependencies
- `get_current_active_user` — standard JWT Bearer auth
- `get_current_active_user_or_service` — JWT or X-Service-Key (for daemons/crons)
- `get_user_from_token_or_query` — JWT from header or `?token=` query param (for `<img>`/stream endpoints)

## Database
- Async SQLAlchemy with `asyncpg` driver
- Alembic migrations — always use `IF NOT EXISTS` for safety
- Models in `backend/app/models/`
- AES-256 encryption for sensitive fields (messages, contacts)

## LLM Providers
- Default: Gemini (`gemini-3.1-flash-lite-preview`)
- DO NOT USE dead models: `gemini-3-pro-preview`, `gemini-2.0-flash`, `text-embedding-004`
- Embeddings: `gemini-embedding-001` (768 dims via Matryoshka)
- Intent routing: Cerebras `llama3.1-8b`

## Config
- All config via `app/config.py` Settings class (pydantic-settings, reads .env)
- Never hardcode secrets — always use `settings.FIELD_NAME`
