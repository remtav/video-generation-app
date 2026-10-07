#!/usr/bin/env bash
# Phase 0 benchmark matrix. Usage: ./run_matrix.sh path/to/start_image.jpg
set -euo pipefail
cd "$(dirname "$0")"
# Recommended on 24 GB cards: reduces fragmentation during the 720p VAE decode.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
IMAGE="${1:?pass a start image for the i2v runs}"

# 1. Fastest config that fits: is full-GPU placement possible at draft size?
python bench.py --mode t2v --preset draft --offload none --repeat 2 || true
# 2. Recommended default: model CPU offload + VAE tiling.
python bench.py --mode t2v --preset draft --offload model --repeat 2
python bench.py --mode t2v --preset standard --offload model --repeat 2
# 3. Effect of VAE tiling at 720p.
python bench.py --mode t2v --preset standard --offload model --no-vae-tiling || true
# 4. Image-to-video.
python bench.py --mode i2v --image "$IMAGE" --preset draft --offload model
python bench.py --mode i2v --image "$IMAGE" --preset standard --offload model
# 5. Quality reference (50 steps) for visual comparison.
python bench.py --mode t2v --preset reference --offload model
# 6. Lower-resolution draft alternative (outside TI2V-5B's training sizes): compare quality.
python bench.py --mode t2v --preset draft480 --offload model

python summarize.py
