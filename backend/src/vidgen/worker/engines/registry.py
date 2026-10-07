from vidgen.config import Settings
from vidgen.worker.engines.base import VideoEngine
from vidgen.worker.engines.fake import FakeEngine


def create_engine(settings: Settings) -> VideoEngine:
    if settings.engine == "fake":
        return FakeEngine(step_delay=settings.fake_step_delay)
    if settings.engine == "wan":
        # Imported lazily: only the GPU worker image has torch and diffusers.
        from vidgen.worker.engines.wan import WanEngine

        return WanEngine(
            settings.wan_model_id,
            offload=settings.wan_offload,
            vae_tiling=settings.wan_vae_tiling,
        )
    raise ValueError(f"unknown engine: {settings.engine}")
