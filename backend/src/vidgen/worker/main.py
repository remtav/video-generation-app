"""arq worker: loads the video engine once, keeps it warm, and runs one job at a time.

Run with ``arq vidgen.worker.main.WorkerSettings``.
"""

import asyncio
import contextlib
import logging
import os
import signal
from typing import Any, ClassVar

from arq import cron, func
from arq.connections import RedisSettings
from arq.constants import in_progress_key_prefix

from vidgen.config import get_settings
from vidgen.db.session import make_engine, make_sessionmaker
from vidgen.keys import WORKER_HEARTBEAT_KEY
from vidgen.storage import LocalStorage
from vidgen.worker.engines import VideoEngine, create_engine
from vidgen.worker.tasks import WorkerDeps, generate_video, reconcile_jobs
from vidgen.worker_status import WorkerState, heartbeat_payload

log = logging.getLogger("vidgen.worker")


def detect_device() -> str:
    """Name of the CUDA device if torch with CUDA is installed, else "cpu"."""
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return str(torch.cuda.get_device_name(0))
    return "cpu"


async def _heartbeat_loop(ctx: dict[str, Any]) -> None:
    interval = get_settings().heartbeat_interval_s
    engine: VideoEngine = ctx["engine"]
    while True:
        state: WorkerState = ctx["engine_state"]
        payload = heartbeat_payload(
            engine=engine.name,
            capabilities=engine.capabilities,
            device=ctx["device"],
            state=state,
        )
        try:
            await ctx["redis"].set(WORKER_HEARTBEAT_KEY, payload, ex=int(interval * 3))
        except Exception:
            log.exception("failed to publish heartbeat")
        await asyncio.sleep(interval)


async def _clear_stale_in_progress(ctx: dict[str, Any]) -> None:
    """At startup no job can be running here, so arq's in-progress markers are stale.

    Clearing them lets arq retry a job interrupted by a crash right away instead of after
    its in-progress timeout (the longest job timeout, i.e. about an hour). This assumes
    this is the only worker on this Redis, which holds for the single-GPU deployment.
    """
    redis = ctx["redis"]
    async for key in redis.scan_iter(match=in_progress_key_prefix + "*"):
        await redis.delete(key)
        log.warning("cleared stale arq marker %s", key.decode() if isinstance(key, bytes) else key)


async def after_job_end(ctx: dict[str, Any]) -> None:
    # An exception escaping an arq job hook crashes the worker's main loop.
    try:
        deps: WorkerDeps | None = ctx.get("deps")
        if deps is not None and deps.restart_requested:
            # Exit cleanly; Docker's restart policy brings up a fresh process with a clean GPU.
            log.warning("restarting worker to release GPU memory")
            os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        log.exception("after_job_end failed")


async def startup(ctx: dict[str, Any]) -> None:
    # arq only configures its own logger; make ours visible too.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    settings = get_settings()
    engine = create_engine(settings)
    db_engine = make_engine(settings.database_url)
    storage = LocalStorage(settings.storage_dir)
    storage.ensure_root()
    ctx["db_engine"] = db_engine
    ctx["engine"] = engine
    ctx["device"] = detect_device()
    ctx["engine_state"] = "loading"
    ctx["deps"] = WorkerDeps(
        settings=settings,
        engine=engine,
        sessionmaker=make_sessionmaker(db_engine),
        storage=storage,
    )
    # Publish "loading" while weights load (first start downloads tens of GB).
    ctx["heartbeat"] = asyncio.create_task(_heartbeat_loop(ctx))

    await _clear_stale_in_progress(ctx)
    log.info("loading engine %r on %s", engine.name, ctx["device"])
    await asyncio.to_thread(engine.load)
    ctx["engine_state"] = "ready"
    log.info("engine %r ready", engine.name)


async def shutdown(ctx: dict[str, Any]) -> None:
    task: asyncio.Task[None] | None = ctx.get("heartbeat")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    with contextlib.suppress(Exception):
        await ctx["redis"].delete(WORKER_HEARTBEAT_KEY)
    if "db_engine" in ctx:
        await ctx["db_engine"].dispose()


async def ping(ctx: dict[str, Any]) -> str:
    """Trivial job used to check the queue end to end."""
    return f"pong from {ctx['engine'].name}"


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        func(
            generate_video,
            # Backstop only: the job enforces its own deadline at step boundaries, and needs
            # extra time to decode and encode the video afterwards.
            timeout=_settings.generation_timeout_s + 900,
            # One retry if the worker crashes mid-job; a second crash fails the job.
            max_tries=2,
        ),
        func(ping, timeout=10, max_tries=1),
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(
            reconcile_jobs,
            minute=set(range(0, 60, 10)),
            run_at_startup=True,
            timeout=120,
            max_tries=1,
        ),
    ]
    on_startup = startup
    on_shutdown = shutdown
    after_job_end = after_job_end
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    # One GPU: never run two generations at once.
    max_jobs = 1
