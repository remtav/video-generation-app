"""Generation presets and hard parameter limits for Wan 2.2 TI2V-5B on a 24 GB RTX 3090.

Time estimates are derived from published RTX 4090 measurements scaled to the 3090 and
from FLOP counts of the actual models (see docs/BENCHMARKS.md). They will be replaced by
measurements from the Phase 0 benchmark kit.
"""

from dataclasses import dataclass
from typing import Literal

PresetName = Literal["draft", "standard"]
AspectRatio = Literal["16:9", "9:16"]

FPS = 24
# Upper bounds enforced by the API regardless of preset (24 GB VRAM budget, sane runtimes).
MAX_STEPS = 60
MIN_GUIDANCE, MAX_GUIDANCE = 1.0, 10.0
MAX_PROMPT_CHARS = 2000

# Wan's recommended negative prompt (English translation of the official default).
DEFAULT_NEGATIVE_PROMPT = (
    "bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, "
    "images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, "
    "incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, "
    "misshapen limbs, fused fingers, still picture, messy background, three legs, many people "
    "in the background, walking backwards"
)


@dataclass(frozen=True)
class Preset:
    name: PresetName
    label: str
    description: str
    # Landscape (16:9) size; portrait swaps width and height. TI2V-5B is trained at
    # 1280x704 / 704x1280 only, so presets vary length and steps, not resolution.
    width: int
    height: int
    num_frames: int
    steps: int
    guidance_scale: float
    # RTX 3090 estimates (model CPU offload, fp32 VAE with tiling, CFG): seconds per
    # denoising step, for the VAE decode, and fixed overhead (offload transfers, text
    # encoding, MP4 encoding).
    est_step_s: float
    est_decode_s: float
    est_overhead_s: float

    def size(self, aspect_ratio: AspectRatio) -> tuple[int, int]:
        if aspect_ratio == "9:16":
            return self.height, self.width
        return self.width, self.height

    @property
    def duration_s(self) -> float:
        return self.num_frames / FPS

    def est_seconds(self, steps: int | None = None) -> int:
        steps = self.steps if steps is None else steps
        return round(steps * self.est_step_s + self.est_decode_s + self.est_overhead_s)


PRESETS: dict[PresetName, Preset] = {
    "draft": Preset(
        name="draft",
        label="Draft",
        description="720p, 2 s clip, 20 steps. Quick previews to iterate on prompts.",
        width=1280,
        height=704,
        num_frames=49,
        steps=20,
        guidance_scale=5.0,
        est_step_s=6.7,
        est_decode_s=63,
        est_overhead_s=10,
    ),
    "standard": Preset(
        name="standard",
        label="Standard",
        description="720p, 5 s clip, 30 steps. Wan 2.2's native length.",
        width=1280,
        height=704,
        num_frames=121,
        steps=30,
        guidance_scale=5.0,
        est_step_s=23,
        est_decode_s=155,
        est_overhead_s=12,
    ),
}


def get_preset(name: object) -> Preset | None:
    """Look up a preset by name, tolerating unknown or missing values from stored params."""
    return next((p for p in PRESETS.values() if p.name == name), None)
