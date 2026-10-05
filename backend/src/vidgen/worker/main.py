"""arq worker: loads the video engine once and keeps it warm.

Run with ``arq vidgen.worker.main.WorkerSettings``. Generation jobs are added in Phase 2.
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any, ClassVar

from arq.connections import RedisSettings

from vidgen.config import get_settings
from vidgen.keys import WORKER_HEARTBEAT_KEY
from vidgen.worker.engines import VideoEngine, create_engine

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


def heartbeat_payload(engine: VideoEngine, device: str) -> str:
    return json.dumps(
        {
            "engine": engine.name,
            "capabilities": sorted(engine.capabilities),
            "device": device,
            "ts": time.time(),
        }
    )


async def _heartbeat_loop(ctx: dict[str, Any]) -> None:
    interval = get_settings().heartbeat_interval_s
    while True:
        payload = heartbeat_payload(ctx["engine"], ctx["device"])
        await ctx["redis"].set(WORKER_HEARTBEAT_KEY, payload, ex=int(interval * 3))
        await asyncio.sleep(interval)


async def startup(ctx: dict[str, Any]) -> None:
    # arq only configures its own logger; make ours visible too.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    settings = get_settings()
    engine = create_engine(settings)
    log.info("loading engine %r", engine.name)
    await asyncio.to_thread(engine.load)
    ctx["engine"] = engine
    ctx["device"] = detect_device()
    log.info("engine %r ready on %s", engine.name, ctx["device"])
    ctx["heartbeat"] = asyncio.create_task(_heartbeat_loop(ctx))


async def shutdown(ctx: dict[str, Any]) -> None:
    task: asyncio.Task[None] | None = ctx.get("heartbeat")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await ctx["redis"].delete(WORKER_HEARTBEAT_KEY)


async def ping(ctx: dict[str, Any]) -> str:
    """Trivial job used to check the queue end to end."""
    return f"pong from {ctx['engine'].name}"


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # One GPU: never run two generations at once.
    max_jobs = 1
