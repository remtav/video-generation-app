# Phase 0 spike: Wan 2.2 TI2V-5B on an RTX 3090

This kit measures real generation speed, VRAM and RAM on the target machine (Linux, RTX 3090 24 GB, 64 GB RAM). The numbers decide the app's presets and memory config.

## Setup
```bash
cd spikes/wan22
python3 -m venv .venv && source .venv/bin/activate
# CUDA build of PyTorch (pick the CUDA version matching your driver, see pytorch.org)
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
python check_env.py          # must print READY
```
The first run downloads about 35 GB into `~/.cache/huggingface`. Set `HF_HOME` to use a different disk.

## Run
Run a single quick test first (the app's Draft preset: 1280×704, 49 frames, 20 steps; estimated ~3.5 min on a 3090):
```bash
python bench.py --mode t2v --preset draft
```
Then run the full matrix, which takes roughly 2 hours (estimates in `docs/BENCHMARKS.md`):
```bash
./run_matrix.sh path/to/any_photo.jpg
python summarize.py > ../../docs/BENCHMARKS.md
```
Watch the GPU in another terminal with `watch -n1 nvidia-smi`.

## Options
| Flag | Meaning |
|------|---------|
| `--mode t2v\|i2v` | text-to-video or image-to-video (`--image` required) |
| `--preset draft\|standard\|reference\|draft480` | 1280×704/49f/20 steps · 1280×704/121f/30 · 1280×704/121f/50 · 832×480/81f/20 |
| `--width --height --frames --steps` | override the preset (sizes are multiples of 32, frames are 4k+1) |
| `--offload none\|model\|sequential` | where the weights live: `model` is the expected default on 24 GB |
| `--no-vae-tiling` | turn off tiled VAE decoding, to measure its effect |
| `--repeat N` | several runs after one model load, so warm timings can be measured |

Each run appends one line to `results.jsonl` and writes the clip to `outputs/`. Both are git-ignored. Please share the summary table and a couple of clips back.

## What to look for
- Does `--offload none` fit at all? If it does, it is the fastest option.
- Seconds per step on a warm run, which drives the app's time estimates.
- Visual quality of 20 vs 30 vs 50 steps, which decides the step counts for the presets.
- Any OOM at 720p, and whether VAE tiling fixes it (untiled fp32 decode at 720p is expected to need ~26 GB).
- `decode_s`: the VAE decode is estimated at ~2.5 min for a 5 s 720p clip, a large share of the total.
- Whether `draft480` looks good enough to replace the 720p draft (it is faster but outside the trained sizes).
