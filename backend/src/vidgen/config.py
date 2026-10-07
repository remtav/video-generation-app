"""Settings shared by the API and the worker, read from VIDGEN_* environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDGEN_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://vidgen:vidgen@localhost:5432/vidgen"
    redis_url: str = "redis://localhost:6379/0"
    # Generated videos, thumbnails and uploads; shared volume between API and worker.
    storage_dir: Path = Path("./data")

    engine: Literal["fake", "wan"] = "fake"
    # Seconds the FakeEngine sleeps per step, to make progress visible in dev.
    fake_step_delay: float = 0.05

    # Wan 2.2 engine (GPU worker only).
    wan_model_id: str = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
    # none: everything on the GPU; model: components moved to the GPU on demand (default,
    # fits 24 GB at 720p); sequential: lowest VRAM, much slower.
    wan_offload: Literal["none", "model", "sequential"] = "model"
    wan_vae_tiling: bool = True

    # A generation still denoising after this long is stopped and marked failed.
    generation_timeout_s: float = 45 * 60

    heartbeat_interval_s: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
