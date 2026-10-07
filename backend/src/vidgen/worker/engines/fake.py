"""CPU-only stand-in engine for development and CI: renders a seeded moving gradient."""

import time

import numpy as np

from vidgen.worker.engines.base import GeneratedVideo, GenerationRequest, ProgressCallback


class FakeEngine:
    name = "fake"
    capabilities = frozenset({"t2v", "i2v"})

    def __init__(self, step_delay: float = 0.0) -> None:
        self.step_delay = step_delay

    def load(self) -> None:
        pass

    def generate(self, req: GenerationRequest, on_progress: ProgressCallback) -> GeneratedVideo:
        for step in range(1, req.steps + 1):
            if self.step_delay:
                time.sleep(self.step_delay)
            on_progress(step, req.steps)

        rng = np.random.default_rng(req.seed)
        phase = rng.uniform(0, 1, size=3).astype(np.float32)
        x = np.linspace(0, 1, req.width, dtype=np.float32)[None, :, None]
        y = np.linspace(0, 1, req.height, dtype=np.float32)[:, None, None]
        # Render frame by frame into uint8: a 720p clip stays ~330 MB instead of ~1.3 GB.
        frames = np.empty((req.num_frames, req.height, req.width, 3), dtype=np.uint8)
        for i, t in enumerate(np.linspace(0, 1, req.num_frames, dtype=np.float32)):
            frame = 0.5 + 0.5 * np.sin(2 * np.pi * (x + y + t + phase))
            frames[i] = (frame * 255).astype(np.uint8)
        return GeneratedVideo(frames=frames, fps=req.fps)
