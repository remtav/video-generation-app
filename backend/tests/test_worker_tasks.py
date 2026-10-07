"""Worker job lifecycle against real Postgres and Redis, using the CPU FakeEngine."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from arq.connections import ArqRedis
from arq.constants import in_progress_key_prefix, result_key_prefix
from arq.jobs import Job as ArqJob
from arq.jobs import JobStatus as ArqJobStatus
from arq.jobs import serialize_result
from arq.worker import JobExecutionFailed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import selectinload

from tests.conftest import DATABASE_URL, REDIS_URL, requires_services
from vidgen.config import Settings
from vidgen.db.models import AssetKind, Job, JobMode, JobStatus
from vidgen.db.session import make_engine, make_sessionmaker
from vidgen.keys import GENERATE_TASK, job_cancel_key
from vidgen.storage import LocalStorage
from vidgen.worker import main as worker_main
from vidgen.worker.engines import EngineOutOfMemory, GeneratedVideo, GenerationRequest
from vidgen.worker.engines.fake import FakeEngine
from vidgen.worker.tasks import OOM_MESSAGE, WorkerDeps, generate_video, reconcile_jobs

pytestmark = [requires_services, pytest.mark.usefixtures("clean_services")]

PARAMS = {
    "preset": "draft",
    "aspect_ratio": "16:9",
    "width": 64,
    "height": 32,
    "num_frames": 9,
    "fps": 24,
    "steps": 4,
    "guidance_scale": 5.0,
    "seed": 7,
    "negative_prompt": "",
}


class BrokenEngine:
    name = "broken"
    capabilities = frozenset({"t2v"})

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def load(self) -> None:
        pass

    def generate(self, req: GenerationRequest, on_progress: Any) -> GeneratedVideo:
        raise self.exc


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    assert DATABASE_URL
    engine = make_engine(DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def arq_redis() -> AsyncIterator[ArqRedis]:
    assert REDIS_URL
    redis = ArqRedis.from_url(REDIS_URL)
    yield redis
    await redis.aclose()


def make_ctx(
    db_engine: AsyncEngine,
    arq_redis: ArqRedis,
    tmp_path: Path,
    *,
    engine: Any = None,
    job_try: int = 1,
    **settings: Any,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {"redis": arq_redis, "job_try": job_try}
    ctx["deps"] = WorkerDeps(
        settings=Settings(**settings),
        engine=engine or FakeEngine(),
        sessionmaker=make_sessionmaker(db_engine),
        storage=LocalStorage(tmp_path),
    )
    return ctx


async def add_job(
    db_engine: AsyncEngine, status: JobStatus = JobStatus.QUEUED, **params: Any
) -> uuid.UUID:
    async with make_sessionmaker(db_engine)() as session:
        job = Job(
            mode=JobMode.T2V,
            engine="fake",
            prompt="a test",
            params={**PARAMS, **params},
            status=status,
        )
        session.add(job)
        await session.commit()
        return job.id


async def load(db_engine: AsyncEngine, job_id: uuid.UUID) -> Job:
    async with make_sessionmaker(db_engine)() as session:
        job = await session.scalar(
            select(Job).where(Job.id == job_id).options(selectinload(Job.assets))
        )
        assert job is not None
        return job


async def test_generate_video_success(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine)
    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await generate_video(ctx, str(job_id)) == "succeeded"

    job = await load(db_engine, job_id)
    assert job.status is JobStatus.SUCCEEDED
    assert job.progress == 1.0
    assert job.error is None
    assert job.engine == "fake"
    assert job.started_at is not None and job.finished_at is not None
    assets = {a.kind: a for a in job.assets}
    assert set(assets) == {AssetKind.VIDEO, AssetKind.THUMBNAIL}
    video = assets[AssetKind.VIDEO]
    assert video.content_type == "video/mp4"
    assert video.meta == {
        "width": 64,
        "height": 32,
        "fps": 24,
        "num_frames": 9,
        "duration_s": 0.375,
    }
    path = tmp_path / video.storage_key
    assert path.is_file() and path.stat().st_size == video.size_bytes
    assert (tmp_path / assets[AssetKind.THUMBNAIL].storage_key).is_file()


async def test_cancelled_while_queued_is_skipped(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine, JobStatus.CANCELLED)
    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await generate_video(ctx, str(job_id)) == "skipped"
    assert (await load(db_engine, job_id)).status is JobStatus.CANCELLED


async def test_cancel_flag_set_before_start(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine)
    await arq_redis.set(job_cancel_key(job_id), "1")
    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await generate_video(ctx, str(job_id)) == "cancelled"
    job = await load(db_engine, job_id)
    assert job.status is JobStatus.CANCELLED
    assert job.assets == []
    assert not await arq_redis.exists(job_cancel_key(job_id))


async def test_cancel_during_generation(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine, steps=200)
    ctx = make_ctx(db_engine, arq_redis, tmp_path, engine=FakeEngine(step_delay=0.02))

    async def cancel_soon() -> None:
        await asyncio.sleep(0.6)
        await arq_redis.set(job_cancel_key(job_id), "1")

    canceller = asyncio.create_task(cancel_soon())
    assert await asyncio.wait_for(generate_video(ctx, str(job_id)), timeout=10) == "cancelled"
    await canceller
    job = await load(db_engine, job_id)
    assert job.status is JobStatus.CANCELLED
    # Progress was reported before the cancel landed.
    assert 0 < job.progress < 1


async def test_deadline_fails_the_job(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine, steps=200)
    ctx = make_ctx(
        db_engine,
        arq_redis,
        tmp_path,
        engine=FakeEngine(step_delay=0.02),
        generation_timeout_s=0.2,
    )
    assert await generate_video(ctx, str(job_id)) == "failed"
    job = await load(db_engine, job_id)
    assert job.status is JobStatus.FAILED
    assert job.error is not None and job.error.startswith("Timed out")


async def test_out_of_memory_fails_and_requests_restart(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine)
    ctx = make_ctx(
        db_engine, arq_redis, tmp_path, engine=BrokenEngine(EngineOutOfMemory("CUDA OOM"))
    )
    assert await generate_video(ctx, str(job_id)) == "failed"
    job = await load(db_engine, job_id)
    assert job.error == OOM_MESSAGE
    assert ctx["deps"].restart_requested


async def test_engine_error_is_recorded(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine)
    ctx = make_ctx(db_engine, arq_redis, tmp_path, engine=BrokenEngine(RuntimeError("boom")))
    assert await generate_video(ctx, str(job_id)) == "failed"
    job = await load(db_engine, job_id)
    assert job.status is JobStatus.FAILED
    assert job.error == "RuntimeError: boom"
    assert not ctx["deps"].restart_requested


async def test_invalid_stored_params_fail_cleanly(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    job_id = await add_job(db_engine, width=65)
    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await generate_video(ctx, str(job_id)) == "failed"
    assert "multiples of 32" in ((await load(db_engine, job_id)).error or "")


@pytest.mark.parametrize(("job_try", "expected"), [(1, "skipped"), (2, "succeeded")])
async def test_only_a_retry_reclaims_a_running_job(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path, job_try: int, expected: str
) -> None:
    job_id = await add_job(db_engine, JobStatus.RUNNING)
    ctx = make_ctx(db_engine, arq_redis, tmp_path, job_try=job_try)
    assert await generate_video(ctx, str(job_id)) == expected


async def test_reconcile_jobs(db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path) -> None:
    lost_queued = await add_job(db_engine)
    orphan_running = await add_job(db_engine, JobStatus.RUNNING)
    retrying = await add_job(db_engine, JobStatus.RUNNING)
    await arq_redis.enqueue_job(GENERATE_TASK, str(retrying), _job_id=str(retrying))
    done = await add_job(db_engine, JobStatus.SUCCEEDED)

    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await reconcile_jobs(ctx) == {"failed": 1, "requeued": 1}

    assert await ArqJob(str(lost_queued), arq_redis).status() is ArqJobStatus.queued
    assert (await load(db_engine, lost_queued)).status is JobStatus.QUEUED
    orphan = await load(db_engine, orphan_running)
    assert orphan.status is JobStatus.FAILED
    assert orphan.error == "The worker stopped while this job was running"
    assert (await load(db_engine, retrying)).status is JobStatus.RUNNING
    assert (await load(db_engine, done)).status is JobStatus.SUCCEEDED


async def store_arq_failure(redis: ArqRedis, job_id: uuid.UUID, result: BaseException) -> None:
    """Write a failed arq result, as arq does when it gives up on a job."""
    data = serialize_result(
        GENERATE_TASK,
        (str(job_id),),
        {},
        1,
        0,
        False,
        result,
        0,
        0,
        "ref",
        "arq:queue",
        str(job_id),
    )
    assert data is not None
    await redis.set(result_key_prefix + str(job_id), data, px=60_000)


async def test_reconcile_explains_why_arq_gave_up(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    timed_out = await add_job(db_engine, JobStatus.RUNNING)
    await store_arq_failure(arq_redis, timed_out, TimeoutError())
    retried_out = await add_job(db_engine, JobStatus.RUNNING)
    await store_arq_failure(arq_redis, retried_out, JobExecutionFailed("max 2 retries exceeded"))

    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await reconcile_jobs(ctx) == {"failed": 2, "requeued": 0}
    assert (await load(db_engine, timed_out)).error == "The job exceeded the worker's time limit"
    assert (await load(db_engine, retried_out)).error == (
        "The worker was interrupted repeatedly while running this job"
    )


async def test_startup_clears_all_stale_in_progress_markers(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    running = await add_job(db_engine, JobStatus.RUNNING)
    await arq_redis.enqueue_job(GENERATE_TASK, str(running), _job_id=str(running))
    await arq_redis.set(in_progress_key_prefix + str(running), b"1", px=3_600_000)
    # Also a job arq picked but the worker died before claiming it in the database.
    await arq_redis.set(in_progress_key_prefix + "unclaimed", b"1", px=3_600_000)
    ctx = make_ctx(db_engine, arq_redis, tmp_path)
    assert await ArqJob(str(running), arq_redis).status() is ArqJobStatus.in_progress

    await worker_main._clear_stale_in_progress(ctx)

    assert await ArqJob(str(running), arq_redis).status() is ArqJobStatus.queued
    assert not await arq_redis.exists(in_progress_key_prefix + "unclaimed")


async def test_restart_requested_during_a_job_fires_after_that_job(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kill = mock.Mock()
    monkeypatch.setattr("os.kill", kill)
    worker_ctx = make_ctx(db_engine, arq_redis, tmp_path)

    # arq gives every job a shallow copy of the worker context.
    await worker_main.after_job_end({**worker_ctx})
    kill.assert_not_called()

    job_ctx = {**worker_ctx}
    job_ctx["deps"].request_restart()
    await worker_main.after_job_end(job_ctx)
    kill.assert_called_once()


async def test_after_job_end_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.kill", mock.Mock(side_effect=OSError("nope")))
    deps = mock.Mock(restart_requested=True)
    await worker_main.after_job_end({"deps": deps})


class TrackingEngine(FakeEngine):
    """Records whether a generation thread is still running."""

    def __init__(self) -> None:
        super().__init__(step_delay=0.02)
        self.active = 0
        self.max_active = 0

    def generate(self, req: GenerationRequest, on_progress: Any) -> GeneratedVideo:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            return super().generate(req, on_progress)
        finally:
            self.active -= 1


async def test_cancelled_job_waits_for_the_engine_thread(
    db_engine: AsyncEngine, arq_redis: ArqRedis, tmp_path: Path
) -> None:
    """An arq timeout or shutdown must not free the GPU slot while the engine still runs."""
    engine = TrackingEngine()
    job_id = await add_job(db_engine, steps=500)
    ctx = make_ctx(db_engine, arq_redis, tmp_path, engine=engine)

    task = asyncio.create_task(generate_video(ctx, str(job_id)))
    await asyncio.sleep(0.3)
    assert engine.active == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert engine.active == 0
    # The row stays running: arq retries the job (shutdown) or reconcile fails it (timeout).
    assert (await load(db_engine, job_id)).status is JobStatus.RUNNING
