"""The engine interface every video model adapter implements."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt
from PIL import Image

from vidgen.db.models import JobMode

# Called after each denoising step with (completed_steps, total_steps).
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class GenerationRequest:
    mode: JobMode
    prompt: str
    width: int
    height: int
    num_frames: int
    steps: int
    seed: int
    fps: int = 24
    negative_prompt: str = ""
    guidance_scale: float = 5.0
    image: Image.Image | None = None

    def __post_init__(self) -> None:
        # Wan 2.2 TI2V-5B: 16x spatial VAE compression x 2x2 patches; 4x temporal compression.
        if self.width % 32 or self.height % 32:
            raise ValueError("width and height must be multiples of 32")
        if self.num_frames < 1 or (self.num_frames - 1) % 4:
            raise ValueError("num_frames must be of the form 4k+1")
        if self.steps < 1:
            raise ValueError("steps must be at least 1")
        if self.mode is JobMode.I2V and self.image is None:
            raise ValueError("image-to-video requires an input image")


@dataclass(frozen=True)
class GeneratedVideo:
    frames: npt.NDArray[np.uint8]  # shape (T, H, W, 3), RGB
    fps: int

    @property
    def duration_s(self) -> float:
        return len(self.frames) / self.fps


class VideoEngine(Protocol):
    name: str
    capabilities: frozenset[str]

    def load(self) -> None:
        """Load weights. Called once at worker startup; the model then stays warm."""

    def generate(self, req: GenerationRequest, on_progress: ProgressCallback) -> GeneratedVideo:
        """Run one generation. Blocking; the worker calls it in a thread."""
        ...
