# Frontend — React/TypeScript/Vite

## Quick Reference
- Build: `npm run build` → `dist/` → copy to `../backend/static/`
- Type check: `npx tsc --noEmit`
- Dev server: `npm run dev` (port 5173)
- API base: `VITE_API_URL` env var or `/api/v1` default

## Design System (MCU JARVIS HUD)
- Background: `#0A0E17` / `#050510`
- Primary: `#00d4ff` (arc-reactor cyan)
- Accent: `#f0a500` (orange/gold)
- Error: `#ef4444`
- Angular borders — NO border-radius (use clip-path or CSS angular shapes)
- `glass-*` CSS classes for frosted glass panels
- Monospace fonts for data readouts
- Corner bracket decorations (SVG overlays)
- Scanline texture overlays

## Key Files
- `src/services/api.ts` — Axios client, JWT interceptor, auto-refresh on 401
- `src/stores/authStore.ts` — Zustand auth state
- `src/pages/` — Page components
- `src/components/` — Reusable components

## Patterns
- Functional components only
- Zustand for global state (no Redux, no Context for state)
- Tailwind CSS (no CSS modules)
- React Router v6 for routing
