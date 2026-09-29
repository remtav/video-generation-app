# Video Generation Web App: Development Plan

> **Engine: Wan 2.2 (Apache-2.0) via Hugging Face Diffusers. Approved 2026-09-29.**
> **Target hardware:** one local NVIDIA RTX 3090 (24 GB VRAM).
> **Licence policy:** model weights must be Apache-2.0 or MIT. No audio in v1.
> See [ENGINE_REVIEW.md](./ENGINE_REVIEW.md) for the review and decision record.

## 1. Product scope

**Goal:** a self-hosted web app where users describe a video (text prompt, optionally a start image) and get back a generated clip. They can track progress, preview it, download it and manage their history.

**MVP features**
- Text-to-video (T2V) and image-to-video (I2V) with Wan 2.2 TI2V-5B.
- Basic parameters: preset, aspect ratio, duration/frames, seed, steps, negative prompt.
- An async job queue with live progress (a single GPU processes one job at a time).
- A gallery/history with download.

**Later features**
- User accounts and quotas.
- Style LoRAs.
- Upscaling and frame interpolation.
- Clip extension/stitching.
- An experimental A14B quality tier.

**Non-goals for v1:** audio, a full video editor, mobile apps, model training UI, multi-GPU or cloud scaling.

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
│ Storage (MinIO / local FS)│ ◀───────── upload mp4/thumb ── │    (Diffusers)   │
└──────────────────────────┘                                 └──────────────────┘
           all services run on the same local machine (Docker Compose)
```

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Frontend | Next.js (React, TypeScript), Tailwind, shadcn/ui, TanStack Query | Mainstream and fast to build |
| API | Python FastAPI + Pydantic, SQLAlchemy + Alembic | Same language as the ML stack, async, typed |
| Queue | Redis + arq (a lightweight async Python queue) | Generation takes minutes, so it must be async. The worker runs with concurrency 1 |
| Worker | Python, PyTorch (CUDA), Diffusers, FFmpeg | Runs Wan 2.2 and encodes/thumbnails output |
| DB | PostgreSQL | Users, jobs, assets |
| Storage | MinIO (S3 API) on local disk | Keeps an S3-compatible path open without depending on a cloud service |
| Realtime | Server-Sent Events | Pushes job progress (step N of M) |
| Infra | Docker Compose + NVIDIA Container Toolkit on the 3090 host | One command starts everything. GPU passthrough is limited to the worker |

**Key abstraction** (`worker/engines/base.py`):
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
- [ ] Prepare the host: NVIDIA driver, CUDA-enabled PyTorch, and the NVIDIA Container Toolkit. Check system RAM; at least 32 GB is recommended.
- [ ] Standalone script `spikes/wan_t2v.py`: Wan 2.2 TI2V-5B via Diffusers, running both T2V and I2V.
- [ ] Benchmark on the 3090 at 480p and 720p, with and without CPU offload, VAE tiling and any speed LoRA. Record time, peak VRAM, peak RAM and quality notes.
- [ ] Licence audit: snapshot the model card and licence of every weight file used into `docs/licenses/`. All of them must be Apache-2.0 or MIT.
- **Exit:**
  - `docs/BENCHMARKS.md` with measured numbers;
  - final preset values;
  - a confirmed memory config that doesn't OOM.

### Phase 1: Project foundations (≈1 week)
- [ ] Monorepo layout: `frontend/`, `api/`, `worker/`, `infra/`, `docs/`.
- [ ] Docker Compose with postgres, redis, minio, api, worker (GPU) and frontend. A `compose.dev.yml` override runs the worker with `FakeEngine`, for machines without a GPU.
- [ ] Model weights live in a host-mounted cache volume (`HF_HOME`) so they download once.
- [ ] Tooling: ruff, mypy and pytest for Python; ESLint, Prettier and Vitest for TypeScript; pre-commit hooks.
- [ ] CI (GitHub Actions): lint, typecheck and unit tests using `FakeEngine`. There is no GPU in CI.
- [ ] DB schema v1: `jobs` (id, status, mode, params JSON, progress, error, timestamps) and `assets` (job_id, kind, storage_key, metadata).
- **Exit:** `docker compose up` brings up the whole stack on the 3090 host, and CI is green.

### Phase 2: MVP text-to-video, end to end (≈2 weeks)
- [ ] API endpoints: `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events` (SSE), `GET /jobs`, `DELETE /jobs/{id}` (which cancels a queued job).
- [ ] `WanEngine` adapter:
  - loads the model once at startup;
  - reports progress from the step callback;
  - encodes H.264 MP4 with FFmpeg and makes a thumbnail;
  - uploads the result to MinIO.
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

### Phase 4: Accounts, quotas and safety (≈1–2 weeks)
*Needed before exposing the app beyond the owner or LAN.*
- [ ] Auth: a simple built-in auth (username/password, argon2 hashing, session cookies), or self-hosted Authentik if SSO is wanted.
- [ ] Per-user job ownership, private-by-default outputs and optional share links.
- [ ] Fair queueing: at most N queued jobs per user and daily GPU-minute quotas, because the single 3090 is the shared bottleneck.
- [ ] Content safety: a prompt blocklist plus an Apache/MIT NSFW image classifier on sampled output frames.
- [ ] Metadata tag noting the video is AI-generated. An optional visible watermark.
- [ ] Remote access without opening router ports, for example Tailscale or a Cloudflare Tunnel. Put a reverse proxy (Caddy) with TLS in front.
- **Exit:** invited users can safely use the app from outside the LAN.

### Phase 5: Advanced generation features (≈2–3 weeks, prioritize with the owner)
- [ ] Post-processing with permissively licensed tools:
  - frame interpolation (e.g. RIFE, MIT) to 48 fps;
  - upscaling with an open-source upscaler (licence checked).
- [ ] Clip extension: take the last frame, continue it with I2V, then stitch with FFmpeg.
- [ ] Style LoRAs: a curated, licence-checked list that users can select.
- [ ] Experimental **A14B quality tier** (GGUF Q4–Q6 with block swapping) as an opt-in "overnight" preset.
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
- A second GPU or cloud burst workers consuming the same queue. The architecture already supports this.
- Audio (would need a new engine that passes the licence bar).

## 4. Timeline summary

| Phase | Duration | Cumulative |
|-------|----------|-----------|
| 0 Engine spike (3090) | 1 wk | 1 wk |
| 1 Foundations | 1 wk | 2 wk |
| 2 MVP T2V | 2 wk | 4 wk |
| 3 I2V + history | 2 wk | 6 wk |
| 4 Accounts + safety | 1–2 wk | ~7.5 wk |
| 5 Advanced features | 2–3 wk | ~10 wk |
| 6 Self-hosted hardening | 1–2 wk | ~11.5 wk |

These estimates assume one full-time developer.

## 5. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Minutes per clip on a 3090 | Async queue, live progress, a Draft preset, a warm model and a speed LoRA (if its licence is OK) |
| A single GPU is the bottleneck for all users | Concurrency of 1, per-user queue caps and quotas (Phase 4) |
| OOM at 720p or long clips | CPU offload, VAE tiling, hard parameter limits, restart on OOM, and limits validated in Phase 0 |
| Ampere lacks FP8 | Use BF16 or GGUF instead of FP8 checkpoints |
| Licence creep via add-ons (LoRAs, upscalers) | Every weight file must be listed in `docs/licenses/` with Apache/MIT proof before it is merged |
| Wan's open line is frozen at 2.2 | The `VideoEngine` abstraction; watch new Apache/MIT releases |
| Exposing a home machine to the internet | Tailscale or a Cloudflare Tunnel, auth, and no open ports (Phase 4) |
| Development without a GPU (CI, cloud sessions) | `FakeEngine`, so the GPU is only required for Phase 0 and for real runs |

## 6. Open questions
1. Audience: personal use only, or invited users? This decides how early Phase 4 needs to happen.
2. Host OS on the 3090 machine: Linux, or Windows with WSL2? This affects Docker/GPU setup.
3. How much system RAM does the host have? It matters for CPU offload and the A14B tier.
