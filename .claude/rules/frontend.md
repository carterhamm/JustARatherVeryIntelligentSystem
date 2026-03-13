---
paths: "frontend/**"
description: React/TypeScript/Vite frontend conventions for JARVIS
---

# Frontend Rules (React/TypeScript/Vite)

## Stack
- React 18, TypeScript strict, Vite, Tailwind CSS
- State: Zustand stores (`frontend/src/stores/`)
- API client: Axios with JWT interceptor (`frontend/src/services/api.ts`)
- Routing: React Router v6

## Design System (MCU JARVIS HUD)
- Background: `#0A0E17` (deep dark)
- Primary: `#00d4ff` (arc-reactor blue/cyan)
- Accent: `#f0a500` (orange/gold)
- Angular/chamfered borders — NO rounded corners (use `glass-*` classes)
- Monospace data readouts, HUD-style widgets
- Scanline overlays, corner bracket decorations
- Inspiration: Jayse Hansen / Cantina Interactive MCU designs

## Build + Deploy
- `npm run build` → `dist/`
- Copy to backend: `rm -rf ../backend/static && cp -r dist ../backend/static`
- Always run `npx tsc --noEmit` before building

## Patterns
- Pages in `frontend/src/pages/`
- Components in `frontend/src/components/`
- API base: `VITE_API_URL` env var or `/api/v1` default
- Auth tokens in Zustand store, auto-refresh on 401
