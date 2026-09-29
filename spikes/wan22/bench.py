"""Phase 0 benchmark: Wan 2.2 TI2V-5B text/image-to-video on a single GPU.

Each run appends one JSON line to results.jsonl and writes the clip to outputs/.
"""

import argparse
import json
import resource
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanPipeline
from diffusers.utils import export_to_video, load_image

MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
FPS = 24

# Width/height must be multiples of 32; frames must be 4k+1.
PRESETS = {
    "draft": {"width": 832, "height": 480, "frames": 81, "steps": 20},
    "standard": {"width": 1280, "height": 704, "frames": 121, "steps": 30},
    "reference": {"width": 1280, "height": 704, "frames": 121, "steps": 50},
}

DEFAULT_PROMPT = (
    "A golden retriever runs through shallow waves on a sunny beach at sunset, "
    "water splashing, slow motion, cinematic lighting, shallow depth of field."
)
# Wan's recommended negative prompt (translated).
DEFAULT_NEGATIVE = (
    "bright tones, overexposed, static, blurred details, subtitles, style, works, "
    "paintings, images, static, overall gray, worst quality, low quality, JPEG "
    "compression residue, ugly, incomplete, extra fingers, poorly drawn hands, "
    "poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, "
    "still picture, messy background, three legs, many people in the background, "
    "walking backwards"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["t2v", "i2v"], default="t2v")
    p.add_argument("--image", help="start image for i2v")
    p.add_argument("--preset", choices=PRESETS, default="draft")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--frames", type=int)
    p.add_argument("--steps", type=int)
    p.add_argument("--guidance", type=float, default=5.0)
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--negative", default=DEFAULT_NEGATIVE)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--offload",
        choices=["none", "model", "sequential"],
        default="model",
        help="none: all on GPU; model: components moved to GPU on demand; "
        "sequential: lowest VRAM, slowest",
    )
    p.add_argument("--no-vae-tiling", action="store_true")
    p.add_argument("--repeat", type=int, default=1, help="runs after one model load")
    p.add_argument("--out", type=Path, default=Path(__file__).parent)
    return p.parse_args()


def build_pipeline(mode: str, offload: str, vae_tiling: bool):
    # The Wan VAE is kept in fp32 for quality, as in the official example.
    vae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)
    cls = WanImageToVideoPipeline if mode == "i2v" else WanPipeline
    pipe = cls.from_pretrained(MODEL_ID, vae=vae, torch_dtype=torch.bfloat16)
    if offload == "model":
        pipe.enable_model_cpu_offload()
    elif offload == "sequential":
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.to("cuda")
    if vae_tiling and hasattr(pipe.vae, "enable_tiling"):
        pipe.vae.enable_tiling()
    return pipe


def peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # KB on Linux


def main() -> None:
    args = parse_args()
    cfg = dict(PRESETS[args.preset])
    for key in ("width", "height", "frames", "steps"):
        if getattr(args, key) is not None:
            cfg[key] = getattr(args, key)
    if cfg["width"] % 32 or cfg["height"] % 32 or (cfg["frames"] - 1) % 4:
        raise SystemExit("width/height must be multiples of 32 and frames must be 4k+1")
    if args.mode == "i2v" and not args.image:
        raise SystemExit("--image is required for i2v")

    out_dir = args.out / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = args.out / "results.jsonl"

    t0 = time.perf_counter()
    pipe = build_pipeline(args.mode, args.offload, not args.no_vae_tiling)
    load_s = time.perf_counter() - t0
    print(f"Model loaded in {load_s:.1f}s")

    extra = {}
    if args.mode == "i2v":
        extra["image"] = load_image(args.image).resize((cfg["width"], cfg["height"]))

    for run in range(args.repeat):
        step_times: list[float] = []
        last = [time.perf_counter()]

        def on_step(_pipe, step, _timestep, kwargs):
            now = time.perf_counter()
            step_times.append(now - last[0])
            last[0] = now
            print(f"  step {step + 1}/{cfg['steps']}  {step_times[-1]:.2f}s", end="\r")
            return kwargs

        torch.cuda.reset_peak_memory_stats()
        generator = torch.Generator(device="cpu").manual_seed(args.seed + run)
        status, error = "ok", None
        t1 = time.perf_counter()
        try:
            frames = pipe(
                prompt=args.prompt,
                negative_prompt=args.negative,
                width=cfg["width"],
                height=cfg["height"],
                num_frames=cfg["frames"],
                num_inference_steps=cfg["steps"],
                guidance_scale=args.guidance,
                generator=generator,
                callback_on_step_end=on_step,
                **extra,
            ).frames[0]
        except torch.cuda.OutOfMemoryError as exc:
            status, error = "oom", str(exc).splitlines()[0]
        gen_s = time.perf_counter() - t1

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        video_path = None
        if status == "ok":
            video_path = out_dir / f"{stamp}_{args.mode}_{args.preset}_s{args.seed + run}.mp4"
            export_to_video(frames, str(video_path), fps=FPS)

        record = {
            "timestamp": stamp,
            "gpu": torch.cuda.get_device_name(0),
            "mode": args.mode,
            "preset": args.preset,
            **cfg,
            "guidance": args.guidance,
            "offload": args.offload,
            "vae_tiling": not args.no_vae_tiling,
            "seed": args.seed + run,
            "status": status,
            "error": error,
            "load_s": round(load_s, 1) if run == 0 else None,
            "generate_s": round(gen_s, 1),
            # The first step includes warm-up; the median excludes it.
            "median_step_s": round(sorted(step_times[1:])[len(step_times[1:]) // 2], 2)
            if len(step_times) > 1
            else None,
            "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
            "peak_ram_gb": round(peak_rss_gb(), 2),
            "video": str(video_path) if video_path else None,
        }
        with results.open("a") as f:
            f.write(json.dumps(record) + "\n")
        print(f"\nRun {run + 1}: {status}, {gen_s:.1f}s, peak VRAM {record['peak_vram_gb']} GB")


if __name__ == "__main__":
    main()
