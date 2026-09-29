# Video Generation Web App: Development Plan

> **Engine choice is PENDING VALIDATION** (see [ENGINE_REVIEW.md](./ENGINE_REVIEW.md)).
> This plan assumes the recommended engine, **Wan 2.2 via Diffusers**, but the architecture keeps the engine behind an interface so a different choice only changes the worker adapter.

## 1. Product scope

**Goal:** a web app where users describe a video (text prompt, optionally a start image) and get back a generated clip. They can track progress, preview it, download it and manage their history.

**MVP features**
- Text-to-video and image-to-video.
- Basic parameters: resolution, duration/frames, seed, steps, negative prompt, aspect ratio.
- An async job queue with live progress.
- A gallery/history with download.

**Later features**
- User accounts and quotas.
- Presets and LoRA styles.
- Upscaling and frame interpolation.
- Clip extension/stitching.
- Audio (only if an audio-capable engine is approved).

**Non-goals for v1:** a full video editor, mobile apps, model training UI.

## 2. Architecture

```
┌────────────┐   HTTPS/JSON + SSE   ┌──────────────┐   enqueue   ┌─────────┐
│  Frontend  │ ───────────────────▶ │  API server  │ ──────────▶ │  Redis  │
│ (Next.js)  │ ◀─── progress/SSE ── │  (FastAPI)   │ ◀── events ─│ (queue) │
└────────────┘                      └──────┬───────┘             └────┬────┘
      ▲                                    │ SQL                      │ jobs
      │ signed URLs                 ┌──────▼──────┐          ┌────────▼────────┐
      └──────────────────────────── │  Postgres   │          │   GPU worker(s)  │
                                    └─────────────┘          │ VideoEngine API  │
┌──────────────────────────┐                                 │  └ WanEngine     │
│ Object storage (MinIO/S3)│ ◀────────── upload mp4/thumb ── │  (Diffusers)     │
└──────────────────────────┘                                 └──────────────────┘
```

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Frontend | Next.js (React, TypeScript), Tailwind, shadcn/ui, TanStack Query | Mainstream, fast to build, SSR for the gallery and sharing pages |
| API | Python FastAPI + Pydantic, SQLAlchemy + Alembic | Same language as the ML stack, async, typed |
| Queue | Redis + a Python worker queue (arq or Celery) | Generation is long-running (tens of seconds to minutes), so it must be async |
| Worker | Python, PyTorch, Diffusers, FFmpeg | Runs the engine and encodes/thumbnails output |
| DB | PostgreSQL | Users, jobs, assets, quotas |
| Storage | MinIO locally, any S3-compatible store in prod | Videos are large, so we serve them via signed URLs |
| Realtime | Server-Sent Events (or WebSocket) | Pushes job progress (step N of M) |
| Infra | Docker Compose (dev), plus GPU host(s) with the NVIDIA container toolkit | Reproducible. GPU workers scale separately from the API |

**Key abstraction** (`worker/engines/base.py`):
```python
class VideoEngine(Protocol):
    name: str
    capabilities: set[str]          # {"t2v", "i2v", "audio", ...}
    def load(self) -> None: ...
    def generate(self, req: GenerationRequest,
                 on_progress: Callable[[int, int], None]) -> GeneratedVideo: ...
```

## 3. Implementation phases

Each phase ends with a **demoable deliverable** and exit criteria.

### Phase 0: Engine validation and spike (≈1 week)
*Precondition: the engine choice has been approved.*
- [ ] Set up a GPU environment (local card or rented 24 GB, e.g. RTX 4090/A10/L4).
- [ ] Run Wan 2.2 TI2V-5B through Diffusers in a standalone script, for both T2V and I2V.
- [ ] Benchmark time, peak VRAM and quality at 480p and 720p, with and without the speed LoRA or quantization.
- [ ] Record the licence check (model card snapshot) in `docs/`.
- **Exit:** a documented benchmark table, a chosen default preset (resolution, steps, frames) and confirmed hardware sizing.

### Phase 1: Project foundations (≈1 week)
- [ ] Monorepo layout: `frontend/`, `api/`, `worker/`, `infra/`, `docs/`.
- [ ] Docker Compose with postgres, redis, minio, api, worker and frontend. The worker has a CPU "fake engine" mode for development without a GPU.
- [ ] Tooling: ruff, mypy and pytest for Python; ESLint, Prettier and Vitest for TypeScript; pre-commit hooks.
- [ ] CI (GitHub Actions): lint, typecheck and unit tests. No GPU in CI; use the fake engine.
- [ ] DB schema v1: `jobs` (id, status, params JSON, progress, error, timestamps) and `assets` (job_id, kind, storage_key, metadata).
- **Exit:** `docker compose up` brings up the whole stack, and CI is green.

### Phase 2: MVP text-to-video, end to end (≈2 weeks)
- [ ] API: `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events` (SSE), `GET /jobs`, `DELETE /jobs/{id}`.
- [ ] Worker: `WanEngine` adapter that loads the model once and keeps it warm, reports progress via a step callback, encodes MP4 (H.264) with FFmpeg, generates a thumbnail and uploads to storage.
- [ ] Job lifecycle: queued → running → succeeded/failed/cancelled, with timeouts and retry on worker crash.
- [ ] Frontend: prompt form (prompt, negative prompt, aspect ratio, duration, seed), progress bar, video player, download button.
- [ ] Input validation, parameter limits and a simple global concurrency limit.
- **Exit:** a user types a prompt and watches progress, then plays and downloads the result. This runs on a real GPU.

### Phase 3: Image-to-video, history and UX (≈2 weeks)
- [ ] Image upload (validation, resize/crop to the target aspect) and an I2V mode.
- [ ] Gallery/history page with pagination, re-run with the same params, "remix" (edit params) and delete.
- [ ] Presets (fast draft, standard, quality) that map to steps, resolution and LoRA.
- [ ] Queue position display and estimated time remaining.
- [ ] Prompt helpers: examples and an optional prompt-enhancer hook (off by default).
- **Exit:** T2V and I2V both work, and users can browse and re-run past generations.

### Phase 4: Accounts, quotas and safety (≈2 weeks)
- [ ] Auth (e.g. Auth.js on the frontend with JWT to the API, or self-hosted Keycloak/Authentik).
- [ ] Per-user job ownership, private-by-default outputs and shareable links.
- [ ] Rate limits and daily GPU-second quotas per user; admin override.
- [ ] Content safety: a prompt blocklist or open-source text classifier, plus an open-source NSFW image classifier on sampled output frames. Abuse reporting.
- [ ] Terms of use and a notice on AI-generated content. Embed C2PA/metadata or a visible watermark (configurable).
- **Exit:** a multi-user deployment is safe to expose to invited users.

### Phase 5: Advanced generation features (≈2–3 weeks, prioritize with the owner)
- [ ] Higher-quality tier with the Wan 2.2 A14B models on a larger GPU pool, routed by preset.
- [ ] Post-processing: open-source upscaling (e.g. Real-ESRGAN) and frame interpolation (RIFE) up to 24–48 fps.
- [ ] Clip extension: last frame → I2V continuation, then stitch.
- [ ] Style LoRAs: a curated list that users can select.
- [ ] Optional second engine through the `VideoEngine` interface (e.g. Kandinsky 5 Lite for drafts, or LTX-2.3 for audio if its licence is accepted).
- **Exit:** feature flags per capability, each benchmarked.

### Phase 6: Production hardening and deployment (≈2 weeks)
- [ ] Deployment target, which depends on budget:
  - a single GPU VM running Docker Compose;
  - Kubernetes with a GPU node pool and autoscaling on queue depth;
  - serverless GPU workers (RunPod or Modal) consuming the same queue.
- [ ] Observability: structured logs, Prometheus/Grafana metrics (queue depth, GPU utilization, job duration, failure rate) and Sentry-style error tracking.
- [ ] Storage lifecycle (auto-expire old outputs), backups and a CDN for video delivery.
- [ ] Load test on the queue and API. Chaos test for worker restarts.
- [ ] Security review: secrets, CORS, upload hardening, dependency scanning.
- **Exit:** a production environment with runbooks, dashboards and alerts.

## 4. Timeline summary

| Phase | Duration | Cumulative |
|-------|----------|-----------|
| 0 Engine spike | 1 wk | 1 wk |
| 1 Foundations | 1 wk | 2 wk |
| 2 MVP T2V | 2 wk | 4 wk |
| 3 I2V + history | 2 wk | 6 wk |
| 4 Accounts + safety | 2 wk | 8 wk |
| 5 Advanced features | 2–3 wk | ~11 wk |
| 6 Production | 2 wk | ~13 wk |

These estimates assume one full-time developer.

## 5. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| GPU cost: the engine is free but compute is not | The small 5B default, distillation LoRAs, quotas and scale-to-zero serverless workers |
| Slow generations hurt UX | Async queue, live progress, a fast draft preset and a warm model |
| Wan's open line is frozen at 2.2 | The `VideoEngine` abstraction; watch other releases (LTX, Kandinsky, MAGI) |
| Licence drift or misreading | Snapshot model-card licences in `docs/licenses/` and re-check before upgrading any model |
| Misuse / harmful content | Phase 4 safety layer, auth before any public launch, watermarking/metadata |
| OOM / VRAM fragmentation | One model per worker process, worker restart on OOM, bounded resolution and frames |

## 6. Open questions for the owner
1. Engine approval (see ENGINE_REVIEW.md §4).
2. Target hardware and budget.
3. Audience: a personal/internal tool or a public multi-user service? This decides how early Phase 4 has to happen.
4. Is audio required?
