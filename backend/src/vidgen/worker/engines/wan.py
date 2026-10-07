"""Wan 2.2 TI2V-5B via Hugging Face diffusers (GPU worker).

Behaviour this adapter relies on was verified against diffusers 0.40 with a tiny random
pipeline (see tests/test_wan_engine.py):

- ``callback_on_step_end(pipe, i, t, kwargs)`` runs once per step and must return a dict;
  an exception raised there propagates out of ``__call__`` unchanged, which is how
  cancellation and the deadline stop a run before the (expensive) VAE decode.
- ``output_type="np"`` frames are float32 in [0, 1], shaped (frames, height, width, 3).
- Sizes must be multiples of 32 (VAE x16, patch x2) and frame counts 4k+1, which
  GenerationRequest already enforces; diffusers would otherwise silently round them.
"""

import gc
import logging
from collections.abc import Callable
from typing import Any, Literal

import numpy as np

from vidgen.worker.engines.base import (
    EngineOutOfMemory,
    GeneratedVideo,
    GenerationRequest,
    ProgressCallback,
)

log = logging.getLogger("vidgen.worker.wan")

Offload = Literal["none", "model", "sequential"]
# Builds the pipeline; replaced in tests with a tiny random one.
PipelineFactory = Callable[[], Any]


def _is_oom(exc: BaseException) -> bool:
    try:
        import torch
    except ImportError:  # pragma: no cover - torch is always present with this engine
        return False
    return isinstance(exc, torch.OutOfMemoryError)


class WanEngine:
    name = "wan"
    # Image-to-video arrives in Phase 3.
    capabilities = frozenset({"t2v"})

    def __init__(
        self,
        model_id: str,
        *,
        offload: Offload = "model",
        vae_tiling: bool = True,
        pipeline_factory: PipelineFactory | None = None,
    ) -> None:
        self.model_id = model_id
        self.offload = offload
        self.vae_tiling = vae_tiling
        self._factory = pipeline_factory or self._load_pretrained
        self._pipe: Any = None

    def _load_pretrained(self) -> Any:
        import torch
        from diffusers import AutoencoderKLWan, WanPipeline

        # The Wan VAE stays in float32 for quality, as in the official examples.
        vae = AutoencoderKLWan.from_pretrained(self.model_id, subfolder="vae", dtype=torch.float32)
        return WanPipeline.from_pretrained(self.model_id, vae=vae, dtype=torch.bfloat16)

    def load(self) -> None:
        import torch

        pipe = self._factory()
        if torch.cuda.is_available():
            if self.offload == "model":
                pipe.enable_model_cpu_offload()
            elif self.offload == "sequential":
                pipe.enable_sequential_cpu_offload()
            else:
                pipe.to("cuda")
        else:
            log.warning("CUDA is not available; running Wan on the CPU (tests only)")
            pipe.to("cpu")
        if self.vae_tiling:
            pipe.vae.enable_tiling()
        pipe.set_progress_bar_config(disable=True)
        self._pipe = pipe

    def generate(self, req: GenerationRequest, on_progress: ProgressCallback) -> GeneratedVideo:
        import torch

        if self._pipe is None:
            raise RuntimeError("WanEngine.load() must be called first")
        pipe = self._pipe

        def callback(_pipe: Any, step: int, _t: Any, _kwargs: dict[str, Any]) -> dict[str, Any]:
            # May raise GenerationCancelled / GenerationTimeout to stop the run.
            on_progress(step + 1, req.steps)
            return {}

        try:
            output = pipe(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt or None,
                height=req.height,
                width=req.width,
                num_frames=req.num_frames,
                num_inference_steps=req.steps,
                guidance_scale=req.guidance_scale,
                # A CPU generator makes seeds reproducible regardless of offloading.
                generator=torch.Generator(device="cpu").manual_seed(req.seed),
                output_type="np",
                callback_on_step_end=callback,
            )
        except BaseException as exc:
            # The pipeline skips its own end-of-call offload when interrupted; restore it so
            # the next run starts with the weights where the offload hooks expect them.
            pipe.maybe_free_model_hooks()
            if _is_oom(exc):
                self._release_memory()
                raise EngineOutOfMemory(str(exc)) from exc
            raise
        finally:
            self._release_memory()

        frames = np.asarray(output.frames[0])
        video = (frames * 255.0).round().clip(0, 255).astype(np.uint8)
        return GeneratedVideo(frames=video, fps=req.fps)

    @staticmethod
    def _release_memory() -> None:
        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
