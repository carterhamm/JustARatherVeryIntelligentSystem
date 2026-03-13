---
name: deploy
description: Full deploy pipeline — build frontend, copy to backend/static, railway up
disable-model-invocation: true
argument-hint: "[skip-frontend]"
allowed-tools: Bash(npm *), Bash(rm *), Bash(cp *), Bash(railway *), Bash(curl *)
---

# Deploy to Production

Run the full deployment pipeline for JARVIS.

## Steps

1. **Build frontend** (unless `$ARGUMENTS` is "skip-frontend" or "backend-only"):
   ```bash
   cd frontend && npm run build
   ```

2. **Copy to backend/static**:
   ```bash
   rm -rf backend/static && cp -r frontend/dist backend/static
   ```

3. **Deploy to Railway**:
   ```bash
   cd backend && railway up --detach
   ```

4. **Wait 60 seconds then verify**:
   ```bash
   sleep 60 && curl -s https://app.malibupoint.dev/health
   ```

If any step fails, stop and report the error. Do NOT continue deploying broken code.

If `$ARGUMENTS` is "skip-frontend" or "backend-only", skip steps 1-2 and deploy backend only.
