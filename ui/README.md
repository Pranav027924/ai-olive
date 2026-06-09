# AI-OLive UI (Phase 8)

Vite + React + TS + Tailwind, with shadcn-style components, TanStack Query
for server state, Zustand for local UI state, and Playwright for end-to-end
flows.

## Dev loop

```bash
cd ui
npm install          # one-time
npm run dev          # vite dev server on http://127.0.0.1:5173
```

The dev server proxies:

- `/api/chat/*` → `http://127.0.0.1:8001` (chat-service)
- `/api/dashboard/*` → `http://127.0.0.1:8004` (dashboard-service)

so make sure both Python services are running:

```bash
make up && make up-analytics
make migrate-all && make migrate-clickhouse
uv run uvicorn chat_service.interfaces.http.app:app --port 8001 --reload
uv run uvicorn dashboard_service.interfaces.http.app:app --port 8004 --reload
```

## Quality gates

```bash
npm run lint
npm run typecheck
npm test                # vitest component / unit
npm run test:e2e        # playwright end-to-end (needs the backend up)
```

## Generated OpenAPI types

```bash
npm run openapi:gen     # writes src/api/__generated__/{chat,dashboard}.ts
```

The hand-mirrored types in [src/api/types.ts](src/api/types.ts) are the
ones the app imports; the generated files are for diffing only, so they
are gitignored.
