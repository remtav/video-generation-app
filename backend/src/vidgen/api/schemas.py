"""Request and response models for the HTTP API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from vidgen.db.models import AssetKind, Job, JobMode, JobStatus
from vidgen.presets import (
    MAX_GUIDANCE,
    MAX_PROMPT_CHARS,
    MAX_STEPS,
    MIN_GUIDANCE,
    AspectRatio,
    Preset,
    PresetName,
    get_preset,
)

MAX_SEED = 2**32 - 1


class JobCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    negative_prompt: str | None = Field(
        default=None,
        max_length=MAX_PROMPT_CHARS,
        description="Omit to use Wan's recommended negative prompt.",
    )
    preset: PresetName = "draft"
    aspect_ratio: AspectRatio = "16:9"
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED, description="Random if omitted.")
    steps: int | None = Field(default=None, ge=1, le=MAX_STEPS, description="Preset default.")
    guidance_scale: float | None = Field(default=None, ge=MIN_GUIDANCE, le=MAX_GUIDANCE)

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class PresetOut(BaseModel):
    name: PresetName
    label: str
    description: str
    width: int
    height: int
    num_frames: int
    fps: int
    duration_s: float
    steps: int
    guidance_scale: float
    est_seconds: int

    @classmethod
    def from_preset(cls, preset: Preset, fps: int) -> "PresetOut":
        return cls(
            name=preset.name,
            label=preset.label,
            description=preset.description,
            width=preset.width,
            height=preset.height,
            num_frames=preset.num_frames,
            fps=fps,
            duration_s=round(preset.duration_s, 2),
            steps=preset.steps,
            guidance_scale=preset.guidance_scale,
            est_seconds=preset.est_seconds(),
        )


class JobOut(BaseModel):
    id: uuid.UUID
    status: JobStatus
    mode: JobMode
    engine: str
    prompt: str
    params: dict[str, Any]
    progress: float
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    queue_position: int | None
    # Estimated total run time on the target GPU for this preset and step count.
    est_seconds: int | None
    video_url: str | None
    thumbnail_url: str | None

    @classmethod
    def from_job(cls, job: Job, *, queue_position: int | None, kinds: set[AssetKind]) -> "JobOut":
        base = f"/api/jobs/{job.id}"
        preset = get_preset(job.params.get("preset"))
        steps = job.params.get("steps")
        return cls(
            id=job.id,
            status=job.status,
            mode=job.mode,
            engine=job.engine,
            prompt=job.prompt,
            params=job.params,
            progress=job.progress,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            queue_position=queue_position,
            est_seconds=(
                preset.est_seconds(steps if isinstance(steps, int) else None) if preset else None
            ),
            video_url=f"{base}/video" if AssetKind.VIDEO in kinds else None,
            thumbnail_url=f"{base}/thumbnail" if AssetKind.THUMBNAIL in kinds else None,
        )


class JobList(BaseModel):
    items: list[JobOut]
    # Pass as ?before= to get the next (older) page; null when there are no more jobs.
    next_cursor: datetime | None
