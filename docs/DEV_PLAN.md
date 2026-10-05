# Video Generation Web App: Development Plan

> **Engine: Wan 2.2 (Apache-2.0) via Hugging Face Diffusers. Approved 2026-09-29.**
> **Target hardware:** one local NVIDIA RTX 3090 (24 GB VRAM).
> **Licence policy:** model weights must be Apache-2.0 or MIT. No audio in v1.
> **Host:** Linux, 64 GB RAM. **Audience:** personal, single user.
> See [ENGINE_REVIEW.md](./ENGINE_REVIEW.md) for the review and decision record.

## 1. Product scope

**Goal:** a self-hosted, personal web app where the owner describes a video (text prompt, optionally a start image) and gets back a generated clip. They can track progress, preview it, download it and manage their history.

**MVP features**
- Text-to-video (T2V) and image-to-video (I2V) with Wan 2.2 TI2V-5B.
- Basic parameters: preset, aspect ratio, duration/frames, seed, steps, negative prompt.
- An async job queue with live progress (the GPU processes one job at a time; the owner can queue several).
- A gallery/history with download.

**Later features**
- Style LoRAs.
- Upscaling and frame interpolation.
- Clip extension/stitching.
- An experimental A14B quality tier.

**Non-goals for v1:** multi-user accounts, quotas, audio, a full video editor, mobile apps, model training UI, multi-GPU or cloud scaling.

## 2. Architecture

```
┌────────────┐   HTTP/JSON + SSE    ┌──────────────┐   enqueue   ┌─────────┐
│  Frontend  │ ───────────────────▶ │  API server  │ ──────────▶ │  Redis  │
│ (Next.js)  │ ◀─── progress/SSE ── │  (FastAPI)   │ ◀── events ─│ (queue) │
└────────────┘                      └──────┬───────┘             └────┬────┘
      ▲                                    │ SQL                      │ 1 job at a time
      │ video URLs                  ┌──────▼──────┐          ┌────────▼─────────┐
      └──────────────────────────── │  Postgres   │          │ GPU worker (3090)│
                                    └─────────────┘          │ VideoEngine API  │
┌──────────────────────────┐                                 │  └ WanEngine     │
│ Storage (local volume)   │ ◀────────── write mp4/thumb ── │    (Diffusers)   │
└──────────────────────────┘                                 └──────────────────┘
           all services run on the same local machine (Docker Compose)
```

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Frontend | Next.js (React, TypeScript), Tailwind, shadcn/ui, TanStack Query | Mainstream and fast to build |
| API | Python FastAPI + Pydantic, SQLAlchemy + Alembic | Same language as the ML stack, async, typed |
| Queue | Redis + arq (a lightweight async Python queue) | Generation takes minutes, so it must be async. The worker runs with concurrency 1 |
| Worker | Python, PyTorch (CUDA), Diffusers, FFmpeg | Runs Wan 2.2 and encodes/thumbnails output |
| DB | PostgreSQL | Jobs, assets, settings |
| Storage | A Docker volume shared by the API and worker (`LocalStorage`) | Simplest option for a single host. The storage interface leaves room for an S3 backend later. MinIO was dropped because its community edition no longer ships prebuilt images |
| Realtime | Server-Sent Events | Pushes job progress (step N of M) |
| Infra | Docker Compose + NVIDIA Container Toolkit on the Linux 3090 host | One command starts everything. GPU passthrough is limited to the worker |

**Key abstraction** (`backend/src/vidgen/worker/engines/base.py`):
```python
class VideoEngine(Protocol):
    name: str
    capabilities: set[str]          # {"t2v", "i2v"}; later maybe "audio"
    def load(self) -> None: ...
    def generate(self, req: GenerationRequest,
                 on_progress: Callable[[int, int], None]) -> GeneratedVideo: ...
```
Implementations:
- `WanEngine`: the real engine.
- `FakeEngine`: CPU-only. It returns a synthetic clip so development and CI work without a GPU.

### RTX 3090 memory strategy (to be confirmed in Phase 0)
- TI2V-5B transformer in **BF16** (≈10 GB).
- UMT5-XXL text encoder offloaded to CPU with `enable_model_cpu_offload()` (it only runs once per job).
- **VAE tiling/slicing** so 720p decoding fits in memory.
- No FP8 compute on Ampere. Use GGUF/INT8 only if VRAM gets tight.
- Keep the model resident between jobs (warm worker). Call `torch.cuda.empty_cache()` after each job, and restart the worker on OOM.
- Optional speedups:
  - SDPA or SageAttention;
  - `torch.compile`;
  - a 4–8-step distillation LoRA, only if its licence is Apache/MIT.

### Planned presets (numbers are estimates until Phase 0 benchmarks)
| Preset | Resolution | Frames (≈ duration) | Steps | Expected time on 3090 |
|--------|-----------|---------------------|-------|------------------------|
| Draft | ~832×480 | 81 (~3.4 s @24fps) | 4–8 with distill LoRA, else ~20 | ~1 min |
| Standard | 1280×704 (Wan 5B native 720p) | 121 (~5 s @24fps) | ~30 | several minutes |
| Quality (experimental, Phase 5) | 720p, A14B GGUF | 81 | ~40 | 10+ min |

## 3. Implementation phases

Each phase ends with a **demoable deliverable** and exit criteria.

### Phase 0: Engine spike on the RTX 3090 (≈1 week)
- [ ] Prepare the Linux host: NVIDIA driver, CUDA-enabled PyTorch, and the NVIDIA Container Toolkit (64 GB RAM is confirmed).
- [x] Spike kit in `spikes/wan22/`: environment check, a T2V/I2V benchmark script for Wan 2.2 TI2V-5B via Diffusers, and a results summarizer. See `spikes/wan22/README.md`.
- [ ] Run the benchmark matrix on the 3090.
- [ ] Benchmark on the 3090 at 480p and 720p, with and without CPU offload, VAE tiling and any speed LoRA. Record time, peak VRAM, peak RAM and quality notes.
- [ ] Licence audit: snapshot the model card and licence of every weight file used into `docs/licenses/`. All of them must be Apache-2.0 or MIT.
- **Exit:**
  - `docs/BENCHMARKS.md` with measured numbers;
  - final preset values;
  - a confirmed memory config that doesn't OOM.

### Phase 1: Project foundations (≈1 week)
- [x] Monorepo layout:
  - `backend/` is one Python project with `vidgen.api`, `vidgen.worker` and `vidgen.db`, so the API and worker share models and config;
  - `frontend/`, `docs/` and `spikes/`.
- [x] Docker Compose (`compose.yml`) with postgres, redis, a one-shot `migrate`, api, worker (CPU `FakeEngine`) and frontend. `compose.gpu.yml` swaps in the CUDA worker image on the 3090 host.
- [x] Model weights live in a host-mounted cache (`MODELS_DIR` → `HF_HOME`) so they download once.
- [x] Tooling: ruff, mypy (strict) and pytest for Python; ESLint, Prettier, `tsc` and Vitest for TypeScript; pre-commit hooks; a `Makefile`.
- [x] CI (GitHub Actions):
  - backend lint, types, a migration round-trip and tests against Postgres and Redis;
  - frontend lint, format, types, tests and build;
  - a full `docker compose` smoke test.
  There is no GPU in CI.
- [x] DB schema v1 (Alembic `0001`): `jobs` (id, status, mode, engine, prompt, params JSONB, progress, error, timestamps) and `assets` (job_id, kind, storage_key, content_type, size, metadata).
- [x] Worker publishes a heartbeat (engine, capabilities, CUDA device). `/api/health` reports every service, and the home page shows it.
- **Exit:** `docker compose up` brings up the whole stack on the 3090 host, and CI is green.

### Phase 2: MVP text-to-video, end to end (≈2 weeks)
- [ ] API endpoints: `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events` (SSE), `GET /jobs`, `DELETE /jobs/{id}` (which cancels a queued job).
- [ ] `WanEngine` adapter:
  - loads the model once at startup;
  - reports progress from the step callback;
  - encodes H.264 MP4 with FFmpeg and makes a thumbnail;
  - writes the result to storage and records `assets` rows.
- [ ] Job lifecycle: queued → running → succeeded/failed/cancelled. Includes a per-job timeout, re-queueing if the worker crashes, and OOM handling that returns a clear error and reloads the worker.
- [ ] Frontend: prompt form (prompt, negative prompt, preset, aspect ratio, seed), queue position, progress bar, video player, download.
- [ ] Hard parameter limits that match what fits on 24 GB.
- **Exit:** from a browser on the LAN, a user types a prompt and watches progress, then plays and downloads a 720p clip generated on the 3090.

### Phase 3: Image-to-video, history and UX (≈2 weeks)
- [ ] Image upload (type and size validation, resize/crop to the target aspect) and an I2V mode on the same TI2V-5B model.
- [ ] Gallery/history page with pagination, re-run with the same seed and params, "remix" (edit params) and delete.
- [ ] Draft and Standard presets wired to the benchmarked values.
- [ ] Time estimate based on each preset's measured average duration.
- [ ] Prompt helpers: example prompts and tips, following Wan's prompt conventions.
- **Exit:** T2V and I2V both work, and users can browse and re-run past generations.

### Phase 4: Secure personal access (≈0.5 week)
*Single user, so there are no accounts, quotas or content moderation.*
- [ ] Bind services to localhost/LAN only. Nothing is exposed to the internet by default.
- [ ] Remote access from your own devices through **Tailscale** (private network, no open router ports).
- [ ] A single-owner login (password hashed with argon2, session cookie) as defence in depth, which can be disabled on the LAN.
- [ ] Metadata tag in output files noting the video is AI-generated.
- **Exit:** the owner can use the app from a phone or laptop away from home, with nothing publicly reachable.

### Phase 5: Advanced generation features (≈2–3 weeks, prioritize with the owner)
- [ ] Post-processing with permissively licensed tools:
  - frame interpolation (e.g. RIFE, MIT) to 48 fps;
  - upscaling with an open-source upscaler (licence checked).
- [ ] Clip extension: take the last frame, continue it with I2V, then stitch with FFmpeg.
- [ ] Style LoRAs: a curated, licence-checked list that users can select.
- [ ] **A14B quality tier** (T2V-A14B / I2V-A14B). 64 GB of RAM makes CPU offload or block swapping workable: try BF16 with offload first, then GGUF Q8/Q6 if that is too slow. Opt-in "quality" preset.
- [ ] Optional second engine through `VideoEngine` if the licence bar allows (e.g. Kandinsky 5 Lite, MIT, as a fast draft engine).
- **Exit:** each feature is behind a flag and benchmarked on the 3090.

### Phase 6: Hardening for self-hosted operation (≈1–2 weeks)
- [ ] Run as a service: Compose `restart: unless-stopped`, health checks, and a startup model warm-up.
- [ ] Observability:
  - structured logs;
  - Prometheus + Grafana (queue depth, job duration, failure rate, GPU utilization/temperature/VRAM via DCGM exporter or nvidia-smi exporter).
- [ ] Disk management: auto-expire old outputs, a storage usage page, and backups of Postgres and chosen outputs.
- [ ] Thermal and power checks on the 3090 during long runs. Optionally cap power (`nvidia-smi -pl`).
- [ ] Security review: secrets in `.env`, CORS, upload hardening, dependency scanning.
- [ ] `docs/RUNBOOK.md`: install, update, model upgrade and troubleshooting (OOM, driver issues).
- **Exit:** the app runs unattended on the 3090 box with dashboards and a runbook.

### Future (out of scope for now)
- Multi-user support (accounts, quotas, content safety), if the app is ever shared.
- A second GPU or cloud burst workers consuming the same queue. The architecture already supports this.
- Audio (would need a new engine that passes the licence bar).

## 4. Timeline summary

| Phase | Duration | Cumulative |
|-------|----------|-----------|
| 0 Engine spike (3090) | 1 wk | 1 wk |
| 1 Foundations | 1 wk | 2 wk |
| 2 MVP T2V | 2 wk | 4 wk |
| 3 I2V + history | 2 wk | 6 wk |
| 4 Secure personal access | 0.5 wk | ~6.5 wk |
| 5 Advanced features | 2–3 wk | ~9 wk |
| 6 Self-hosted hardening | 1–2 wk | ~10.5 wk |

These estimates assume one full-time developer.

## 5. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Minutes per clip on a 3090 | Async queue, live progress, a Draft preset, a warm model and a speed LoRA (if its licence is OK) |
| OOM at 720p or long clips | CPU offload, VAE tiling, hard parameter limits, restart on OOM, and limits validated in Phase 0 |
| Ampere lacks FP8 | Use BF16 or GGUF instead of FP8 checkpoints |
| Licence creep via add-ons (LoRAs, upscalers) | Every weight file must be listed in `docs/licenses/` with Apache/MIT proof before it is merged |
| Wan's open line is frozen at 2.2 | The `VideoEngine` abstraction; watch new Apache/MIT releases |
| Exposing a home machine to the internet | Tailscale only, owner login, and no open ports (Phase 4) |
| Development without a GPU (CI, cloud sessions) | `FakeEngine`, so the GPU is only required for Phase 0 and for real runs |

## 6. Resolved questions (2026-09-29)
1. **Audience:** personal, single user. Phase 4 is reduced to secure remote access.
2. **Host OS:** Linux, with native Docker and the NVIDIA Container Toolkit.
3. **System RAM:** 64 GB, enough for CPU offload and the A14B tier.
