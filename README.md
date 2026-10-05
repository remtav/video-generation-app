# video-generation-app (vidgen)

A self-hosted, personal web app for AI video generation. It runs **Wan 2.2** (Apache-2.0) on a local RTX 3090.

- Plan: [docs/DEV_PLAN.md](docs/DEV_PLAN.md). Engine choice: [docs/ENGINE_REVIEW.md](docs/ENGINE_REVIEW.md).
- Phase 0 GPU benchmark kit: [spikes/wan22/](spikes/wan22/README.md).

## Layout
| Path | What |
|------|------|
| `backend/` | Python (uv): FastAPI API, arq GPU worker, SQLAlchemy models, Alembic migrations |
| `frontend/` | Next.js + Tailwind web UI (proxies `/api/*` to the backend) |
| `compose.yml` | Full stack; the worker runs the CPU `FakeEngine` |
| `compose.gpu.yml` | Override for the RTX 3090 host (CUDA worker image) |
| `docs/` | Plan, engine review, licence register |

## Run
```bash
cp .env.example .env          # set POSTGRES_PASSWORD
make up                       # any machine: CPU FakeEngine
make up-gpu                   # RTX 3090 host (needs NVIDIA Container Toolkit)
open http://127.0.0.1:3000    # status page; API health at :8000/api/health
make down
```

## Develop
```bash
cd backend && uv sync && uv run pytest     # see backend/README.md
cd frontend && npm ci && npm run dev       # see frontend/README.md
make lint test
pip install pre-commit && pre-commit install
```
