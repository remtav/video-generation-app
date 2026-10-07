# Benchmarks: Wan 2.2 TI2V-5B on an RTX 3090

> **Status: ESTIMATES (2026-10-07).** No published measurement of TI2V-5B on an RTX 3090 exists. The numbers below are extrapolated from a measured RTX 4090 run, NVIDIA's spec sheets, and FLOP counts of the actual models. Replace them with measurements from the Phase 0 kit (`spikes/wan22/`, `run_matrix.sh`), then update `backend/src/vidgen/presets.py`.

## Setup assumed
- **Model:** `Wan-AI/Wan2.2-TI2V-5B-Diffusers` through diffusers 0.40, with the transformer in BF16 and the VAE in FP32.
- **Memory config:** model CPU offload and VAE tiling (the defaults in `compose.gpu.yml`).
- **Sampling:** classifier-free guidance at 5.0. diffusers runs two transformer passes per step.
- **Hardware:** RTX 3090, which delivers 71 TFLOPS dense in BF16 (FP32 accumulate) and 35.6 TFLOPS in TF32. There is no FP8. The host has 64 GB RAM.

## Estimated app presets
The presets stay at 1280×704 (or 704×1280 for portrait), the only sizes TI2V-5B is trained at. Draft and Standard differ in clip length and step count instead.

| Preset | Size × frames | Steps | Per step | VAE decode | Overhead | **Total** | Peak VRAM | Host RAM |
|---|---|---|---|---|---|---|---|---|
| Draft | 1280×704 × 49 (2.0 s) | 20 | ~6.7 s | ~63 s | ~10 s | **~3.4 min** | ~13 GB | ~29 GB |
| Standard | 1280×704 × 121 (5.0 s) | 30 | ~23 s (19–28) | ~155 s (140–210) | ~12 s | **~14 min (13–17.5)** | ~17 GB | ~31 GB |
| *Reference (official defaults)* | 1280×704 × 121 | 50 | ~23 s | ~155 s | ~12 s | *~22 min (20–26)* | ~17 GB | ~31 GB |
| *Alternative draft (Phase 0 comparison)* | 832×480 × 81 (3.4 s) | 20 | ~4.4 s | ~46 s | ~10 s | *~2.4 min* | ~13 GB | ~29 GB |

Confidence varies by row:
- **720p per-step times and the Standard and Reference totals:** medium.
- **VAE decode times:** low to medium. They are computed from FLOP counts and were not measured.
- **Both drafts:** low. No 5B measurement exists at these sizes, and 832×480 is outside the trained sizes, so its quality may suffer.

The app computes `est_seconds = steps × per-step + decode + overhead`, so the estimate shown in the UI follows the step count you choose.

## How the numbers were derived
1. **Anchor measurements.**
   - The official Wan 2.2 efficiency table gives TI2V-5B at 720p, 121 frames and 50 steps on one RTX 4090: **534.7 s**, with a 22.9 GB peak.
   - An independent 4090 run of the official script measured **9.92 s per step**.
   - That works out to about 105 TFLOPS effective, roughly 64% of the 4090's 165 TFLOPS BF16 peak.
2. **Tokens.** The count is (frames−1)/4+1 latent frames × H/32 × W/32:
   - 1280×704×121 → 31 × 22 × 40 = **27,280 tokens**;
   - 1280×704×49 → 13 × 22 × 40 = 11,440 tokens;
   - 832×480×81 → 21 × 15 × 26 = 8,190 tokens.
3. **FLOPs.** Counted with `torch.utils.flop_counter` on the real model configs.
   - One transformer forward at 720p/121 frames is 520.7 TFLOP. 54% of that is attention, which grows quadratically with the token count, so shorter clips get cheaper faster than linearly.
   - The draft forward was scaled from the same split: about 150 TFLOP.
4. **Scaling to the 3090.**
   - The BF16 peak ratio between 4090 and 3090 is 2.33×. Measured Wan 2.2 ratios between the two cards range from 1.87× at 480p to 2.88× at 720p.
   - That gives ~23 s per step at 720p (range 19–28 s).
5. **VAE decode.**
   - The Wan 2.2 VAE decoder is heavy: about 3,300 TFLOP for a tiled 720p, 121-frame decode, running in TF32 on the 3090.
   - Tiling is mandatory at 720p. An untiled FP32 decode needs about 26 GB and runs out of memory on 24 GB cards (diffusers #12097, Wan2.2 #90).
   - `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (set in `compose.gpu.yml`) reduces fragmentation. The 4090 reference run needed it to avoid running out of memory during decode.

## Other facts
- **Download:** about 34 GB.
  - Transformer: 20 GB, stored in FP32 and loaded as BF16 (~10 GB).
  - UMT5-XXL text encoder: 11.4 GB.
  - VAE: 2.8 GB.
- **Cold start:** loading the model takes an estimated 40–90 s after the download. The worker keeps it loaded between jobs.
- **Official sampling defaults:** 50 steps, guidance 5.0, flow shift 5.0, 24 fps, 121 frames, and only the 1280×704 / 704×1280 sizes.
- **Speed-ups considered, but none ship:**
  - **Step-distillation LoRAs:** none for TI2V-5B is Apache-2.0 or MIT licensed. lightx2v hasn't released one, the "Turbo" model is CC BY-NC-SA, and the community LoRA extractions declare no licence.
  - **FastWan2.2-TI2V-5B (Apache-2.0):** a full 3-step checkpoint. It needs custom DMD timesteps that the stock diffusers scheduler doesn't support, and even with it the VAE decode would dominate the total time. It is a candidate for Phase 5.
  - **BF16 VAE or larger decode tiles:** could cut decode time by roughly 3× or 27% respectively. Their effect on quality is unverified, so this is a Phase 0/5 experiment.

## Sources
- Wan 2.2 README and efficiency table: https://github.com/Wan-Video/Wan2.2 (https://raw.githubusercontent.com/Wan-Video/Wan2.2/main/assets/comp_effic.png)
- TI2V-5B config (steps, guidance, sizes): https://raw.githubusercontent.com/Wan-Video/Wan2.2/main/wan/configs/wan_ti2v_5B.py
- Model card and files: https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B-Diffusers
- 4090 per-step measurement: https://computingforgeeks.com/run-wan-video-generation-locally/
- 3090 and 4090 Wan 2.2 comparison: https://chimolog.co/bto-gpu-wan22-specs/
- VAE decode memory: https://github.com/huggingface/diffusers/issues/12097 and https://github.com/Wan-Video/Wan2.2/issues/90
- GPU specs: https://www.nvidia.com/content/PDF/nvidia-ampere-ga-102-gpu-architecture-whitepaper-v2.pdf and https://images.nvidia.com/aem-dam/Solutions/geforce/ada/nvidia-ada-gpu-architecture.pdf
- FastWan (Apache-2.0): https://huggingface.co/FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers
- Speed LoRA status: https://huggingface.co/lightx2v/Wan2.2-Lightning and https://huggingface.co/quanhaol/Wan2.2-TI2V-5B-Turbo
