# Backend — FastAPI Python

## Quick Reference
- Entry point: `app/main.py` → `create_app()` factory
- Config: `app/config.py` → `settings` singleton (pydantic-settings, reads .env)
- All routes mounted in `app/api/v1/__init__.py` — prefixes defined THERE only
- Deploy: `railway up --detach` from this directory

## Router Pattern
```python
# In the router file (e.g., camera.py):
router = APIRouter(tags=["Camera"])  # NO prefix here

# In __init__.py:
from app.api.v1.camera import router as camera_router
v1_router.include_router(camera_router, prefix="/camera")  # prefix HERE
```

## Auth Dependencies (app/core/dependencies.py)
- `get_current_active_user` — standard JWT from Authorization header
- `get_current_active_user_or_service` — JWT or X-Service-Key header (crons/daemons)
- `get_user_from_token_or_query` — JWT from header or `?token=` query (streams/img tags)

## Key Directories
- `app/api/v1/` — Route handlers
- `app/services/` — Business logic (chat, heartbeat, research, camera)
- `app/integrations/` — External APIs (Google, ElevenLabs, ESPN, Mac Mini)
- `app/agents/` — LLM agent tools and schemas
- `app/graphrag/` — RAG pipeline (vector store, entity extraction)
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — Pydantic request/response schemas
- `knowledge/` — Markdown files for RAG ingestion

## Testing
```bash
python -c "import ast; ast.parse(open('app/path/to/file.py').read())"
```
