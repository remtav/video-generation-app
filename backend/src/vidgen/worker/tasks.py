"""arq job functions: run one generation, and reconcile jobs after crashes."""

import asyncio
import contextlib
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from arq.connections import ArqRedis
from arq.jobs import Job as ArqJob
from arq.jobs import JobStatus as ArqJobStatus
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vidgen.config import Settings
from vidgen.db.models import Asset, AssetKind, Job, JobMode, JobStatus
from vidgen.jobs import notify_job_changed, thumbnail_key, video_key
from vidgen.keys import GENERATE_TASK, job_cancel_key
from vidgen.storage import LocalStorage
from vidgen.worker.engines import (
    EngineOutOfMemory,
    GeneratedVideo,
    GenerationCancelled,
    GenerationRequest,
    GenerationTimeout,
    VideoEngine,
)
from vidgen.worker.progress import ProgressPump
from vidgen.worker.video import encode_mp4, save_thumbnail

log = logging.getLogger("vidgen.worker")

OOM_MESSAGE = (
    "The GPU ran out of memory. Try the Draft preset or fewer steps; the worker restarts "
    "to free GPU memory."
)
# How long a cancelled job waits for the engine thread to reach its next step (or finish
# the VAE decode, which cannot be interrupted: ~2.5 min at 720p on an RTX 3090).
ENGINE_STOP_GRACE_S = 300.0

# One generation on the GPU at a time, even if arq frees its slot early (it cannot stop
# threads): a second engine call blocks here instead of running out of GPU memory.
_GPU_LOCK = threading.Lock()


@dataclass
class WorkerDeps:
    """Everything a job needs, stored in the arq context at startup.

    arq hands each job a shallow copy of the worker context, so state that must outlive a
    job (like the restart request) lives on this shared object, not in the context dict.
    """

    settings: Settings
    engine: VideoEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: LocalStorage
    restart_requested: bool = False

    def request_restart(self) -> None:
        """Ask the worker process to exit (and be restarted) after the current job."""
        self.restart_requested = True


def _deps(ctx: dict[str, Any]) -> WorkerDeps:
    deps: WorkerDeps = ctx["deps"]
    return deps


def build_request(job: Job) -> GenerationRequest:
    p = job.params
    return GenerationRequest(
        mode=job.mode,
        prompt=job.prompt,
        negative_prompt=p.get("negative_prompt", ""),
        width=int(p["width"]),
        height=int(p["height"]),
        num_frames=int(p["num_frames"]),
        steps=int(p["steps"]),
        guidance_scale=float(p["guidance_scale"]),
        seed=int(p["seed"]),
        fps=int(p.get("fps", 24)),
    )


async def _claim(deps: WorkerDeps, job_id: uuid.UUID, job_try: int) -> Job | None:
    """Atomically move a job to running. Returns None if it should not run (e.g. cancelled).

    A retry after a worker crash finds the job still marked running and may re-claim it.
    """
    claimable = [JobStatus.QUEUED] + ([JobStatus.RUNNING] if job_try > 1 else [])
    async with deps.sessionmaker() as session:
        job = await session.scalar(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(claimable))
            .values(
                status=JobStatus.RUNNING,
                engine=deps.engine.name,
                progress=0.0,
                error=None,
                started_at=func.now(),
                finished_at=None,
            )
            .returning(Job)
        )
        await session.commit()
        return job


async def _finish(
    deps: WorkerDeps,
    job_id: uuid.UUID,
    status: JobStatus,
    *,
    error: str | None = None,
    assets: list[Asset] | None = None,
) -> None:
    async with deps.sessionmaker() as session:
        values: dict[str, Any] = {"status": status, "error": error, "finished_at": func.now()}
        if status is JobStatus.SUCCEEDED:
            values["progress"] = 1.0
        result = await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.RUNNING)
            .values(**values)
            .returning(Job.id)
        )
        if result.first() is not None and assets:
            session.add_all(assets)
        await session.commit()


def _write_outputs(video: GeneratedVideo, storage: LocalStorage, job_id: uuid.UUID) -> list[Asset]:
    """Encode the video and thumbnail to storage (blocking; run in a thread)."""
    height, width = video.frames.shape[1:3]
    meta = {
        "width": int(width),
        "height": int(height),
        "fps": video.fps,
        "num_frames": len(video.frames),
        "duration_s": round(video.duration_s, 3),
    }
    outputs = [
        (AssetKind.VIDEO, video_key(job_id), "video/mp4", encode_mp4),
        (AssetKind.THUMBNAIL, thumbnail_key(job_id), "image/jpeg", save_thumbnail),
    ]
    assets = []
    for kind, key, content_type, write in outputs:
        path = storage.path_for(key)
        write(video, path)
        assets.append(
            Asset(
                job_id=job_id,
                kind=kind,
                storage_key=key,
                content_type=content_type,
                size_bytes=path.stat().st_size,
                meta=meta,
            )
        )
    return assets


def _run_engine(
    engine: VideoEngine, request: GenerationRequest, pump: ProgressPump
) -> GeneratedVideo:
    with _GPU_LOCK:
        return engine.generate(request, pump.callback)


async def _generate(
    engine: VideoEngine, request: GenerationRequest, pump: ProgressPump
) -> GeneratedVideo:
    """Run the engine in a thread without ever leaving it running unattended.

    If this coroutine is cancelled (arq timeout, worker shutdown), stop the engine at its
    next step and wait for the thread before re-raising, so arq only starts another job
    once the GPU is actually free.
    """
    future = asyncio.ensure_future(asyncio.to_thread(_run_engine, engine, request, pump))
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        pump.cancel_requested.set()
        # Ignore the engine's own exception, a repeated cancel, or the grace timeout.
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(asyncio.shield(future), ENGINE_STOP_GRACE_S)
        raise


async def generate_video(ctx: dict[str, Any], job_id_str: str) -> str:
    deps = _deps(ctx)
    redis: ArqRedis = ctx["redis"]
    job_id = uuid.UUID(job_id_str)

    job = await _claim(deps, job_id, ctx.get("job_try", 1))
    if job is None:
        log.info("job %s is no longer queued; skipping", job_id)
        return "skipped"
    await notify_job_changed(redis, job_id)
    log.info("job %s started (try %s)", job_id, ctx.get("job_try", 1))

    pump = ProgressPump(
        job_id, deps.sessionmaker, redis, timeout_s=deps.settings.generation_timeout_s
    )
    status: JobStatus = JobStatus.FAILED
    error: str | None = "Generation failed"
    assets: list[Asset] | None = None
    try:
        if await redis.exists(job_cancel_key(job_id)):
            raise GenerationCancelled
        if job.mode is not JobMode.T2V:
            raise ValueError(f"{job.mode.value} is not supported yet")
        request = build_request(job)
        pump.start()
        video = await _generate(deps.engine, request, pump)
        await pump.stop()
        assets = await asyncio.to_thread(_write_outputs, video, deps.storage, job_id)
        status, error = JobStatus.SUCCEEDED, None
    except GenerationCancelled:
        status, error = JobStatus.CANCELLED, None
    except GenerationTimeout:
        minutes = deps.settings.generation_timeout_s / 60
        error = f"Timed out after {minutes:.0f} minutes"
    except EngineOutOfMemory:
        error = OOM_MESSAGE
        deps.request_restart()
    except Exception as exc:
        log.exception("job %s failed", job_id)
        error = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        # Also stops the engine thread at its next step if we are being cancelled.
        await pump.stop()

    await _finish(deps, job_id, status, error=error, assets=assets)
    await redis.delete(job_cancel_key(job_id))
    await notify_job_changed(redis, job_id)
    log.info("job %s %s%s", job_id, status.value, f": {error}" if error else "")
    return status.value


# arq statuses meaning the job will (still) be run by the worker.
_PENDING_ARQ = {ArqJobStatus.queued, ArqJobStatus.deferred, ArqJobStatus.in_progress}


async def _failure_reason(arq_job: ArqJob) -> str:
    """Explain why arq gave up on a job the database still thinks is active."""
    try:
        info = await arq_job.result_info()
    except Exception:
        info = None
    if info is not None and not info.success:
        if isinstance(info.result, TimeoutError):
            return "The job exceeded the worker's time limit"
        if "retries exceeded" in str(info.result):
            return "The worker was interrupted repeatedly while running this job"
    return "The worker stopped while this job was running"


async def reconcile_jobs(ctx: dict[str, Any]) -> dict[str, int]:
    """Repair the database after crashes, restarts, or lost Redis data.

    With one worker running one job at a time, no generation runs while this does, so a
    job marked running is either waiting for arq's crash retry or orphaned.
    """
    deps = _deps(ctx)
    redis: ArqRedis = ctx["redis"]
    failed = requeued = 0
    async with deps.sessionmaker() as session:
        jobs = (
            await session.scalars(
                select(Job).where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            )
        ).all()
        for job in jobs:
            arq_job = ArqJob(str(job.id), redis)
            arq_status = await arq_job.status()
            if arq_status in _PENDING_ARQ:
                continue
            if job.status is JobStatus.QUEUED and arq_status is ArqJobStatus.not_found:
                await redis.enqueue_job(GENERATE_TASK, str(job.id), _job_id=str(job.id))
                requeued += 1
            else:
                job.status = JobStatus.FAILED
                job.error = await _failure_reason(arq_job)
                job.finished_at = func.now()
                failed += 1
        await session.commit()
    for job in jobs:
        await notify_job_changed(redis, job.id)
    if failed or requeued:
        log.warning("reconciled jobs: %d failed, %d re-queued", failed, requeued)
    return {"failed": failed, "requeued": requeued}
