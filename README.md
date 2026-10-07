# video-generation-app (vidgen)

A self-hosted, personal web app for AI video generation. It runs **Wan 2.2** (Apache-2.0) on a local RTX 3090.

Type a prompt, pick a preset, and watch the clip being generated live. Then play it in the browser or download the MP4.

- Plan: [docs/DEV_PLAN.md](docs/DEV_PLAN.md). Engine choice: [docs/ENGINE_REVIEW.md](docs/ENGINE_REVIEW.md).
- Expected speed on an RTX 3090: [docs/BENCHMARKS.md](docs/BENCHMARKS.md). Draft takes about 3.4 min; Standard (5 s at 720p) about 14 min.
- Phase 0 GPU benchmark kit: [spikes/wan22/](spikes/wan22/README.md).

## Layout
| Path | What |
|------|------|
| `backend/` | Python (uv): FastAPI API, arq GPU worker, SQLAlchemy models, Alembic migrations |
| `frontend/` | Next.js + Tailwind web UI (proxies `/api/*` to the backend) |
| `compose.yml` | Full stack; the worker runs the CPU `FakeEngine` (renders a test pattern) |
| `compose.gpu.yml` | Override for the RTX 3090 host: CUDA worker image running Wan 2.2 |
| `scripts/smoke_test.sh` | End-to-end check of a running stack (submit, live progress, download) |
| `docs/` | Plan, engine review, benchmark estimates, licence register |

## Run
```bash
cp .env.example .env          # set POSTGRES_PASSWORD
make up                       # any machine: CPU FakeEngine (test pattern, seconds per job)
make up-gpu                   # RTX 3090 host: Wan 2.2 (needs the NVIDIA Container Toolkit)
open http://127.0.0.1:3000
make smoke                    # end-to-end check against the running stack
make down
```

**On the GPU host:**
- **First start:** the worker downloads about 34 GB of model weights into the `models` volume. The status badge shows "Loading wan model…" until it is ready, and jobs you submit meanwhile wait in the queue.
- **Later starts:** loading takes about a minute.
- **Logs:** `docker compose logs -f worker`.

## Develop
```bash
cd backend && uv sync && uv run pytest     # see backend/README.md
cd frontend && npm ci && npm run dev       # see frontend/README.md
make lint test
pip install pre-commit && pre-commit install
```
