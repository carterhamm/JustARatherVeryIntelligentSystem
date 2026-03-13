---
name: test
description: Test all modified code — Python syntax, TypeScript types, iOS build
disable-model-invocation: true
argument-hint: "[backend|frontend|ios|all]"
allowed-tools: Bash(python *), Bash(npx *), Bash(npm *), Bash(xcodebuild *), Bash(git *)
---

# Test Modified Code

Run tests on modified files before committing. Target: `$ARGUMENTS` (default: all).

## 1. Identify modified files

```bash
git status --short
```

## 2. Python backend (if `$ARGUMENTS` is "backend" or "all" or empty)

For every modified `.py` file under `backend/`:
```bash
python -c "import ast; ast.parse(open('FILE').read())"
```

## 3. Frontend TypeScript (if `$ARGUMENTS` is "frontend" or "all" or empty)

```bash
cd frontend && npx tsc --noEmit
```

Then build to catch any runtime issues:
```bash
npm run build
```

## 4. iOS (if `$ARGUMENTS` is "ios" or "all" or empty)

Only if files under `JARVIS-iOS/` were modified:
```bash
xcodebuild -project JARVIS-iOS/JARVIS.xcodeproj -scheme JARVIS \
  -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

## Report

After all tests, report which passed/failed. Do NOT proceed with commits if any test fails.
