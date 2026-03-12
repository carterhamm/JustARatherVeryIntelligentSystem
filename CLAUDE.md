# JARVIS Project — Claude Code Instructions

## Workflow: Test, Commit, Deploy

After **every batch of changes**, follow this sequence strictly:

### 1. Test Before Committing
- **Python backend**: Run syntax checks (`python -c "import ast; ast.parse(open(f).read())"`) on all modified files. If there's a test suite, run it.
- **Frontend (React/TS)**: Run `npx tsc --noEmit` to catch type errors. Then `npm run build` in `frontend/`. If either fails, fix and retry until clean.
- **iOS/Watch app**: Run `xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS -destination 'generic/platform=iOS' build` (or equivalent). If it fails, fix and rebuild until `** BUILD SUCCEEDED **`.
- **Alembic migrations**: Verify migration chain is valid and won't crash on deploy (e.g., don't `CREATE TABLE` for tables that already exist — use `IF NOT EXISTS` or stamp the DB).

### 2. Commit to Git
- Stage specific files (not `git add .`) to avoid committing secrets or junk.
- Write clear commit messages describing what changed and why.
- This applies to **all** parts of the project: backend, frontend, iOS, Watch, CLI.

### 3. Push to GitHub
- `git push origin master` after every commit.

### 4. Deploy
- **Backend + frontend**: Copy built frontend to `backend/static/`, then `railway up --detach` from `backend/`.
- **iOS/Watch**: Xcode build verification is sufficient (no CI/CD yet).
- Never consider a task "done" until the deploy is confirmed.

### 5. If Deploy Fails
- Check logs, fix the issue, and repeat the cycle. Don't leave a broken deploy.

## Project Structure

- **Backend**: `backend/` — FastAPI (Python), deployed on Railway
- **Frontend**: `frontend/` — React/TypeScript/Vite, built and copied to `backend/static/`
- **iOS App**: `JARVIS-iOS/` — SwiftUI, Xcode project
- **CLI**: `cli/` — Python package (`malibupoint`), published to PyPI
- **Knowledge**: `backend/knowledge/` — Markdown files for RAG

## Key Commands

```bash
# Frontend build + copy
cd frontend && npm run build && rm -rf ../backend/static && cp -r dist ../backend/static

# Railway deploy
cd backend && railway up --detach

# iOS build check
xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS -destination 'generic/platform=iOS' build

# Python syntax check
python -c "import ast; ast.parse(open('file.py').read())"
```
