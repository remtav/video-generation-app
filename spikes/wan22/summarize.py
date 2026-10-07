"""Turn results.jsonl into a Markdown table for docs/BENCHMARKS.md."""

import json
import sys
from pathlib import Path

COLS = [
    "mode", "preset", "width", "height", "frames", "steps", "offload", "vae_tiling",
    "status", "generate_s", "median_step_s", "decode_s", "peak_vram_gb", "peak_ram_gb",
]


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "results.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit("no results")
    print(f"GPU: {rows[0]['gpu']}\n")
    print("| " + " | ".join(COLS) + " |")
    print("|" + "---|" * len(COLS))
    for r in rows:
        print("| " + " | ".join(str(r.get(c, "")) for c in COLS) + " |")


if __name__ == "__main__":
    main()
