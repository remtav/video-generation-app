# vidgen frontend

Next.js (App Router) + Tailwind + TanStack Query. Browser requests to `/api/*` are proxied to the FastAPI service (set `API_INTERNAL_URL`, default `http://localhost:8000`).

```bash
npm ci
npm run dev            # http://localhost:3000
npm run lint && npm run format:check && npm run typecheck && npm test
```
