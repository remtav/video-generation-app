"""Generation jobs: submit, inspect, follow, cancel, delete, and fetch the resulting media."""

import asyncio
import logging
import secrets
import shutil
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from vidgen.api.deps import ArqDep, RedisDep, SessionDep, SettingsDep, StorageDep
from vidgen.api.schemas import MAX_SEED, JobCreate, JobList, JobOut
from vidgen.db.models import Asset, AssetKind, Job, JobMode, JobStatus
from vidgen.jobs import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    job_dir_key,
    notify_job_changed,
    queue_position,
)
from vidgen.keys import GENERATE_TASK, job_cancel_key
from vidgen.presets import DEFAULT_NEGATIVE_PROMPT, FPS, PRESETS
from vidgen.worker_status import read_worker_status

log = logging.getLogger("vidgen.api")
router = APIRouter(prefix="/jobs", tags=["jobs"])

# A queued job must wait behind every earlier job; keep it in arq's queue long enough.
QUEUE_EXPIRY_S = 30 * 24 * 3600
CANCEL_FLAG_TTL_S = 24 * 3600


async def _get_job(session: SessionDep, job_id: uuid.UUID) -> Job:
    job = await session.scalar(
        select(Job).where(Job.id == job_id).options(selectinload(Job.assets))
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


async def to_out(session: SessionDep, job: Job) -> JobOut:
    return JobOut.from_job(
        job,
        queue_position=await queue_position(session, job),
        kinds={asset.kind for asset in job.assets},
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=JobOut)
async def create_job(
    body: JobCreate,
    session: SessionDep,
    redis: RedisDep,
    arq: ArqDep,
    settings: SettingsDep,
) -> JobOut:
    preset = PRESETS[body.preset]
    width, height = preset.size(body.aspect_ratio)
    params = {
        "preset": preset.name,
        "aspect_ratio": body.aspect_ratio,
        "width": width,
        "height": height,
        "num_frames": preset.num_frames,
        "fps": FPS,
        "steps": body.steps or preset.steps,
        "guidance_scale": body.guidance_scale or preset.guidance_scale,
        "seed": body.seed if body.seed is not None else secrets.randbelow(MAX_SEED + 1),
        "negative_prompt": (
            body.negative_prompt if body.negative_prompt is not None else DEFAULT_NEGATIVE_PROMPT
        ),
    }
    # The worker records the engine it actually used; until then show the one it advertises.
    try:
        engine = (await read_worker_status(redis)).engine or settings.engine
    except Exception:
        engine = settings.engine

    job = Job(mode=JobMode.T2V, engine=engine, prompt=body.prompt, params=params)
    session.add(job)
    await session.commit()

    try:
        await arq.enqueue_job(
            GENERATE_TASK, str(job.id), _job_id=str(job.id), _expires=QUEUE_EXPIRY_S
        )
    except Exception as exc:
        log.exception("failed to enqueue job %s", job.id)
        job.status = JobStatus.FAILED
        job.error = "Could not queue the job (is Redis running?)"
        job.finished_at = func.now()
        await session.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, job.error) from exc

    return await to_out(session, await _get_job(session, job.id))


@router.get("", response_model=JobList)
async def list_jobs(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[datetime | None, Query(description="Cursor from next_cursor")] = None,
) -> JobList:
    query = (
        select(Job)
        .options(selectinload(Job.assets))
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(limit + 1)
    )
    if before is not None:
        query = query.where(Job.created_at < before)
    jobs = list((await session.scalars(query)).all())
    has_more = len(jobs) > limit
    jobs = jobs[:limit]
    return JobList(
        items=[await to_out(session, job) for job in jobs],
        next_cursor=jobs[-1].created_at if has_more else None,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, session: SessionDep) -> JobOut:
    return await to_out(session, await _get_job(session, job_id))


@router.post("/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
async def cancel_job(job_id: uuid.UUID, session: SessionDep, redis: RedisDep) -> JobOut:
    """Cancel a queued job immediately, or ask the worker to stop a running one.

    A running job stops at the next denoising step; follow its events to see it end.
    """
    # Conditional update: never races with the worker claiming the job.
    cancelled = await session.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
        .values(status=JobStatus.CANCELLED, finished_at=func.now())
        .returning(Job.id)
    )
    await session.commit()
    if cancelled is not None:
        await notify_job_changed(redis, job_id)
        return await to_out(session, await _get_job(session, job_id))

    job = await _get_job(session, job_id)
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"job already {job.status.value}")
    await redis.set(job_cancel_key(job_id), "1", ex=CANCEL_FLAG_TTL_S)
    return await to_out(session, job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: uuid.UUID, session: SessionDep, storage: StorageDep) -> Response:
    job = await _get_job(session, job_id)
    if job.status in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "cancel the job before deleting it")
    await session.delete(job)
    await session.commit()
    await asyncio.to_thread(
        shutil.rmtree, storage.path_for(job_dir_key(job_id)), ignore_errors=True
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _asset_response(
    session: SessionDep,
    storage: StorageDep,
    job_id: uuid.UUID,
    kind: AssetKind,
    download_name: str | None = None,
) -> FileResponse:
    asset = await session.scalar(select(Asset).where(Asset.job_id == job_id, Asset.kind == kind))
    path = storage.path_for(asset.storage_key) if asset else None
    if asset is None or path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{kind.value} not found")
    return FileResponse(
        path,
        media_type=asset.content_type,
        filename=download_name,
        # Media never changes for a given job id.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/{job_id}/video", response_class=FileResponse)
async def get_video(
    job_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    download: bool = False,
) -> FileResponse:
    name = f"vidgen-{str(job_id)[:8]}.mp4" if download else None
    return await _asset_response(session, storage, job_id, AssetKind.VIDEO, name)


@router.get("/{job_id}/thumbnail", response_class=FileResponse)
async def get_thumbnail(
    job_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> FileResponse:
    return await _asset_response(session, storage, job_id, AssetKind.THUMBNAIL)
