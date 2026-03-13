# J.A.R.V.I.S. — Claude Code Project Instructions

## Identity
- **Full name**: Just A Rather Very Intelligent System
- **Owner**: Carter Neil Hammond ("Mr. Stark")
- **Domain**: app.malibupoint.dev
- **Repo**: carterhamm/JustARatherVeryIntelligentSystem

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React/TS/Vite)  →  built to backend/static/         │
│  iOS/Watch App (SwiftUI)   →  SSE streaming, passkeys, voice   │
│  CLI (malibupoint/PyPI)    →  terminal JARVIS client            │
├─────────────────────────────────────────────────────────────────┤
│  Backend (FastAPI/Python)  →  Railway (app.malibupoint.dev)     │
│    ├─ WebSocket chat + agentic tool loop (31+ tools)            │
│    ├─ Gemini (default LLM), Claude, Cerebras (intent routing)   │
│    ├─ Twilio voice, ElevenLabs TTS, iMessage via Mac Mini       │
│    ├─ Google OAuth per-user (Gmail, Calendar, Drive)            │
│    ├─ RAG: Qdrant vectors + local knowledge files               │
│    └─ Cron: morning briefing, heartbeat (15m), research (4h)    │
├─────────────────────────────────────────────────────────────────┤
│  Mac Mini M4 (malibupoint.dev subdomains via Cloudflare)        │
│    ├─ LM Studio (Gemma 3 12B) → stark.malibupoint.dev           │
│    ├─ XTTS-v2 voice server  → voice.malibupoint.dev             │
│    ├─ Camera daemon (Tapo)  → camera.malibupoint.dev            │
│    ├─ iMessage daemon       → polls chat.db, replies via AS     │
│    └─ Wake word listener    → "hey jarvis" → backend            │
├─────────────────────────────────────────────────────────────────┤
│  Databases                                                       │
│    ├─ PostgreSQL (Railway)  — users, messages, conversations     │
│    ├─ Redis (Railway)       — cache, audio, research, sessions   │
│    └─ Qdrant Cloud          — vector embeddings (768-dim)        │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

- `backend/` — FastAPI Python backend (deployed on Railway)
- `frontend/` — React/TypeScript/Vite (built → `backend/static/`)
- `JARVIS-iOS/` — SwiftUI iOS + watchOS app
- `cli/` — Python CLI package (`malibupoint`, published to PyPI)
- `backend/knowledge/` — Markdown files for RAG ingestion

## Workflow: Test, Commit, Deploy

After **every batch of changes**, complete this cycle. Never leave undeployed code.

### 1. Test
- **Python**: `python -c "import ast; ast.parse(open('file.py').read())"` on all modified files
- **Frontend**: `npx tsc --noEmit` then `npm run build` — fix until clean
- **iOS**: `xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS -destination 'generic/platform=iOS' build`
- **Alembic**: Use `IF NOT EXISTS` for new tables; verify chain won't crash

### 2. Commit
- `git add` specific files only (never `git add .` — secrets risk)
- Clear commit messages describing what and why

### 3. Push + Deploy
```bash
git push origin master

# Frontend build + copy
cd frontend && npm run build && rm -rf ../backend/static && cp -r dist ../backend/static

# Railway deploy
cd backend && railway up --detach
```

### 4. If deploy fails → check logs, fix, redeploy. Never leave broken.

## Hard Rules

1. **ALWAYS deploy** — no task is done until changes are live on Railway
2. **No impersonation** — JARVIS must NEVER send messages/posts/calls AS the user
3. **No hallucination** — always use tools for factual data, never guess
4. **Stage specific files** — never `git add .` or `git add -A`
5. **Secrets safety** — never commit .env, credentials, API keys
6. **Security first** — no command injection, XSS, SQL injection. Validate at boundaries.

## Key Commands

```bash
# Full deploy pipeline
cd frontend && npm run build && rm -rf ../backend/static && cp -r dist ../backend/static
cd ../backend && railway up --detach

# Railway
railway logs --tail        # check deploy logs
railway variables          # view env vars

# iOS
xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS \
  -destination 'generic/platform=iOS' build

# CLI
cd cli && pipx install . --force
```

## Coding Standards

- **Python**: Type hints, async/await, structlog logging, pydantic models
- **TypeScript**: Strict mode, functional components, Zustand stores
- **SwiftUI**: MVVM, @MainActor for view models, async/await
- **All**: Minimal comments (code should be self-evident), no over-engineering
- **JARVIS personality**: Paul Bettany's JARVIS — dry, British, efficient, 1-2 sentences

## Memory System

Persistent knowledge lives in `~/.claude/projects/.../memory/`. See `MEMORY.md` there
for the index. Topic files contain detailed info that loads on demand. When something is
worth remembering long-term, save it to the appropriate memory file.

Scoped rules in `.claude/rules/` auto-load when editing matching file paths.
