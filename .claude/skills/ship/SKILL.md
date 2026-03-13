---
name: ship
description: Full pipeline — test all, commit, push, build frontend, deploy to Railway, verify
disable-model-invocation: true
argument-hint: "[commit message]"
allowed-tools: Bash(python *), Bash(npx *), Bash(npm *), Bash(git *), Bash(railway *), Bash(curl *), Bash(rm *), Bash(cp *), Bash(sleep *), Bash(xcodebuild *)
---

# Ship It — Full Test + Commit + Deploy Pipeline

Complete end-to-end pipeline. Commit message: `$ARGUMENTS` (or auto-generate from changes).

## 1. Test everything

Run syntax checks on all modified Python files:
```bash
git diff --name-only HEAD | grep '\.py$'
```
For each: `python -c "import ast; ast.parse(open('FILE').read())"`

If frontend files changed:
```bash
cd frontend && npx tsc --noEmit && npm run build
```

If iOS files changed:
```bash
xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS \
  -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

**STOP if any test fails.** Fix first, then retry.

## 2. Commit + Push

Stage only the relevant files (NEVER `git add .`):
```bash
git add <specific files>
git commit -m "<message>"
git push origin master
```

Use `$ARGUMENTS` as the commit message if provided, otherwise generate one from the changes.
Always append `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`.

## 3. Build + Deploy

```bash
cd frontend && npm run build
rm -rf ../backend/static && cp -r dist ../backend/static
cd ../backend && railway up --detach
```

## 4. Verify

Wait for deploy, then check:
```bash
sleep 60 && curl -s https://app.malibupoint.dev/health
```

Report final status. If deploy fails, diagnose with `railway logs --tail`.
