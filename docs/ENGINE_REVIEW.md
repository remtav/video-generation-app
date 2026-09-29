# Video Generation Engine Review

> **Status: AWAITING VALIDATION.** Recommendation below. Nothing is committed to until the owner approves it.
> Review date: 2026-09-29. Licences and model versions move quickly, so re-check each one against its model card before approving.

## 1. Selection criteria

| # | Criterion | Why it matters |
|---|-----------|----------------|
| C1 | **Open source and free** (hard constraint) | Weights and inference code downloadable at no cost, under an OSI-style licence (Apache-2.0 / MIT) with no revenue caps, region bans or usage gating |
| C2 | Output quality | Motion coherence, prompt adherence, temporal consistency |
| C3 | Hardware footprint | VRAM needed determines hosting cost (the model is free, the GPU is not) |
| C4 | Speed | Seconds per clip affects UX and queue design |
| C5 | Modes | Text-to-video (T2V), image-to-video (I2V), video-to-video, audio |
| C6 | Ecosystem | Diffusers / ComfyUI support, LoRAs, quantized builds, community activity |
| C7 | Longevity | Active maintainer, likelihood of future open releases |

## 2. Candidates

Legend: ✅ meets C1 · ⚠️ free but restricted (not strictly open source) · ❌ fails C1

### 2.1 Wan 2.2 (Alibaba). ✅ Apache-2.0
- **Variants:** TI2V-5B (T2V and I2V, 720p@24fps), T2V-A14B and I2V-A14B (MoE, higher quality), plus a companion Wan-Animate line (Wan-Animate-2 is also Apache-2.0).
- **Pros**
  - A genuinely permissive licence: commercial use with no caps and no region limits.
  - Among the best open-model photorealism, especially for humans (faces, skin, hair).
  - The 5B model runs on consumer GPUs (≈8–12 GB with GGUF/offload, ≈24 GB comfortable); the 14B MoE needs ≈24 GB with FP8 and offload, or ≈80 GB unquantized.
  - Best-in-class ecosystem: first-class support in Diffusers and ComfyUI, many LoRAs, and speed-up distillations (lightx2v / CausVid-style 4–8 step LoRAs).
- **Cons**
  - No native audio.
  - Clips are short (~5 s); longer videos need extension or stitching.
  - **Alibaba has stopped open-sourcing flagship models:** Wan 2.5, 2.6, 2.7 and 3.0 are API-only. 2.2 is probably the last open flagship, so there is no guaranteed upgrade path.
  - The 14B models are slow without distillation (minutes per clip on a single GPU).

### 2.2 LTX-2 / LTX-2.3 (Lightricks). ⚠️ LTX-2 Community License
- **Specs:** 22B DiT. Generates synchronized audio and video in one pass, native up to 4K@50fps, clips up to ~20 s. Distilled variants are very fast.
- **Pros**
  - The only strong open-weights model with **native audio** (including lip-sync).
  - Fastest high-end model; the distilled versions make near-real-time previews possible.
  - Active vendor with frequent releases, plus good ComfyUI and Diffusers support and VFX tooling (keyframes, control, upscalers).
- **Cons**
  - **The licence is not OSI open source:** it is free only for organizations under **$10M ARR**, and larger ones need a paid licence. (Some third-party sites call it Apache-2.0. The official model card is authoritative, so check it.)
  - Heavy: ≈32 GB VRAM for the distilled model and ≈80 GB at full precision. FP8/GGUF builds help.
  - Human realism is slightly below Wan 2.2 in most comparisons.

### 2.3 HunyuanVideo 1.5 (Tencent). ⚠️/❌ Tencent Hunyuan Community License
- **Specs:** ~8.3–13B, 480p/720p T2V and I2V, runs in ≈14 GB with FP8 and offload.
- **Pros:** cinematic motion quality, stable faces under movement, good long-scene coherence, efficient for its quality.
- **Cons:** **the licence does not apply in the EU, UK or South Korea.** It also carries a >100M MAU clause, an attribution requirement and a ban on using outputs to train other models. That makes it unsuitable for a public web app and fails C1.

### 2.4 Mochi 1 (Genmo). ✅ Apache-2.0
- **Specs:** 10B AsymmDiT, 480p, ~5.4 s clips.
- **Pros:** truly open, smooth natural motion, and a good official LoRA fine-tuning trainer.
- **Cons:** it is from 2024 and now behind Wan 2.2 in quality. It is 480p only, heavy (≈20 GB+ at FP8), and has no strong I2V. Development has slowed.

### 2.5 CogVideoX (Zhipu / THUDM). ✅ 2B (Apache-2.0) · ⚠️ 5B (CogVideoX License)
- **Pros:** strong prompt adherence, mature Diffusers integration and many fine-tunes. The 2B model runs in ≈16 GB.
- **Cons:** only the weaker 2B model is Apache-2.0. Output is 720×480 at 6–10 s with 8 fps (1.0) or 16 fps (1.5). Quality is now clearly below the 2025–26 models, and the project is effectively in maintenance.

### 2.6 Open-Sora 2.0 (HPC-AI Tech). ✅ Apache-2.0
- **Pros:** fully open (weights, training code and data pipeline), 11B, 256p/768p, and decent quality for its training budget.
- **Cons:** below Wan 2.2 in quality, a smaller inference ecosystem (weaker ComfyUI/Diffusers support) and high VRAM for 768p.

### 2.7 Other options worth knowing (check each licence before use)
| Model | Licence (as reported) | Notes |
|-------|----------------------|-------|
| Kandinsky 5.0 Video Lite (Sber AI) | MIT | 2B, fast and light. Quality is decent but a notch below Wan 5B/14B |
| MAGI-1 (Sand AI) | Apache-2.0 | Autoregressive chunked generation that is good for long or infinite video. 24B is heavy; a 4.5B variant exists |
| SkyReels V2 (Skywork) | check the model card | Wan-based "infinite length" diffusion-forcing; film-style fine-tunes |
| Step-Video-T2V (StepFun) | MIT | 30B at ≈80 GB VRAM. Too heavy for a cost-efficient web app |

### 2.8 Inference runtime (separate decision)
| Option | Licence | Pros | Cons |
|--------|---------|------|------|
| **Hugging Face Diffusers** | Apache-2.0 | Clean Python API, easy to embed in a worker, supports Wan, LTX, Mochi and CogVideoX | New optimizations arrive later than in ComfyUI |
| ComfyUI (headless API) | GPL-3.0 | Fastest access to new models, quantizations and speed LoRAs; workflows are JSON | Extra process with a less structured API. GPL only matters if we redistribute it (serving over a network is fine) |
| lightx2v / vendor repos | varies | Maximum speed | Tightly coupled to one model |

## 3. Scorecard (1–5, higher is better)

| Model | C1 Licence | C2 Quality | C3 Footprint | C4 Speed | C5 Modes | C6 Ecosystem | C7 Longevity | **Fits constraint?** |
|-------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Wan 2.2** | 5 | 5 | 4 | 3 | 4 | 5 | 3 | **Yes** |
| LTX-2.3 | 2 | 4 | 2 | 5 | 5 | 4 | 5 | Conditional |
| HunyuanVideo 1.5 | 1 | 5 | 4 | 3 | 4 | 4 | 4 | No |
| Mochi 1 | 5 | 3 | 3 | 2 | 2 | 3 | 2 | Yes |
| CogVideoX-2B | 5 | 2 | 4 | 3 | 3 | 4 | 2 | Yes |
| Open-Sora 2.0 | 5 | 3 | 2 | 2 | 3 | 2 | 3 | Yes |
| Kandinsky 5 Lite | 5 | 3 | 5 | 4 | 3 | 3 | 3 | Yes |

## 4. Recommendation (pending approval)

**Primary engine: Wan 2.2 (Apache-2.0), served through Hugging Face Diffusers inside a GPU worker.**
- **Default tier:** `Wan2.2-TI2V-5B` for T2V and I2V at 720p, with a 4–8-step distillation LoRA for speed. It is cheap to host on one 24 GB GPU.
- **Quality tier (optional, later):** `Wan2.2-T2V-A14B` / `I2V-A14B` on a 48–80 GB GPU.

**Why:** it is the only candidate that satisfies the strict "open source and free" constraint while also leading on quality and ecosystem.

**Design hedge:** the backend exposes a pluggable `VideoEngine` interface, so we can:
- add **LTX-2.3** later if native audio becomes a requirement and its licence is acceptable;
- add **Kandinsky 5 Lite** as a fast "draft" engine;
- swap engines if Wan's open line stays frozen.

### Decision needed from you
1. Approve **Wan 2.2** as the primary engine, or pick another.
2. Confirm the licence bar: strictly OSI (Apache/MIT only), or is "free with conditions" such as LTX's under-$10M rule acceptable?
3. Is **native audio** a must-have? If so, LTX-2.3 becomes the main contender.
4. What GPU budget and target do you have: a local GPU (which card?), rented cloud GPUs, or serverless?

## Sources
- https://www.thundercompute.com/blog/best-open-source-ai-video-generation-models
- https://www.hyperstack.cloud/blog/case-study/best-open-source-video-generation-models
- https://www.aimagicx.com/blog/open-source-ai-video-models-comparison-2026
- https://ltx.io/blog/open-source-video-generation-models-guide
- https://invideo.io/blog/open-source-image-models-licenses/
- https://invideo.io/blog/ltx-ai-video-generator/
- https://magichour.ai/blog/ltx-2-3-vs-wan-2-2
- https://localaimaster.com/blog/wan-2-7-open-source
- https://canirun.ai/license/tencent-hunyuan-community/
- https://comfyui-wiki.com/en/models/hunyuan/hunyuan-1-5
