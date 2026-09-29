"""Check that the host is ready to run Wan 2.2: GPU, CUDA, RAM, disk and libraries."""

import importlib
import platform
import shutil
import sys

import psutil


def main() -> int:
    ok = True
    print(f"Python      : {sys.version.split()[0]} ({platform.system()})")
    ram_gb = psutil.virtual_memory().total / 1e9
    print(f"System RAM  : {ram_gb:.1f} GB")
    free_gb = shutil.disk_usage(".").free / 1e9
    print(f"Free disk   : {free_gb:.1f} GB (TI2V-5B download is ~35 GB incl. text encoder)")
    if free_gb < 60:
        print("  WARNING: less than 60 GB free; model cache may not fit.")

    for mod in ("diffusers", "transformers", "accelerate", "imageio_ffmpeg"):
        try:
            m = importlib.import_module(mod)
            print(f"{mod:<12}: {getattr(m, '__version__', 'ok')}")
        except ImportError:
            print(f"{mod:<12}: MISSING")
            ok = False

    try:
        import torch
    except ImportError:
        print("torch       : MISSING (install a CUDA build)")
        return 1

    print(f"torch       : {torch.__version__} (CUDA {torch.version.cuda})")
    if not torch.cuda.is_available():
        print("CUDA        : NOT AVAILABLE")
        return 1
    props = torch.cuda.get_device_properties(0)
    print(f"GPU         : {props.name}, {props.total_memory / 1e9:.1f} GB, sm_{props.major}{props.minor}")
    print(f"BF16        : {'yes' if torch.cuda.is_bf16_supported() else 'no'}")
    if props.major < 9 and (props.major, props.minor) < (8, 9):
        print("FP8 compute : no (Ampere); use BF16 / GGUF, not FP8 checkpoints")

    try:
        from diffusers import WanImageToVideoPipeline, WanPipeline  # noqa: F401

        print("Wan pipelines: available")
    except ImportError:
        print("Wan pipelines: MISSING (upgrade diffusers)")
        ok = False

    print("\nREADY" if ok else "\nNOT READY")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
