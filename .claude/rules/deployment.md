---
description: Deployment pipeline and Railway configuration
---

# Deployment Rules

## Railway Configuration
- Project: jarvis, Environment: production, Service: backend
- Domain: app.malibupoint.dev
- CLI linked — `railway up --detach` from `backend/` directory

## Deploy Pipeline
1. Test all modified code (Python syntax, TS types, iOS build)
2. Build frontend: `cd frontend && npm run build`
3. Copy: `rm -rf ../backend/static && cp -r dist ../backend/static`
4. Commit + push: `git add <files> && git commit && git push origin master`
5. Deploy: `cd backend && railway up --detach`
6. Verify: `curl https://app.malibupoint.dev/health`

## Environment Variables
- All secrets on Railway (never in code): API keys, tokens, DB URLs
- Config loaded via pydantic-settings `Settings` class in `app/config.py`
- Use `railway variables` to check, `railway variables --set "KEY=value"` to update

## Cron Services (Railway)
- morning-cron: `45 12 * * *` UTC (6:45 AM MDT)
- heartbeat-cron: `*/15 * * * *` (every 15 min)
- research-cron: `0 */4 * * *` (every 4 hours)
- All POST to `/api/v1/cron/{endpoint}` with `X-Service-Key` header

## If Deploy Fails
- `railway logs --tail` to diagnose
- Fix, recommit, redeploy. Never leave production broken.
