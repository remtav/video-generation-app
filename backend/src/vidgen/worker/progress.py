"""Bridge between the engine thread and the event loop while one job runs.

The engine calls ``callback`` from its thread after every step. The callback only records
progress and checks for cancellation or the deadline; an async ``pump`` writes progress
to the database (throttled), notifies SSE listeners, and polls the cancel flag.
"""

import asyncio
import contextlib
import logging
import threading
import time
import uuid

from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vidgen.db.models import Job, JobStatus
from vidgen.jobs import notify_job_changed
from vidgen.keys import job_cancel_key
from vidgen.worker.engines import GenerationCancelled, GenerationTimeout

log = logging.getLogger("vidgen.worker")


class ProgressPump:
    def __init__(
        self,
        job_id: uuid.UUID,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        timeout_s: float,
        interval_s: float = 0.5,
    ) -> None:
        self.job_id = job_id
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.interval_s = interval_s
        self.deadline = time.monotonic() + timeout_s
        self.cancel_requested = threading.Event()
        self._latest = 0.0
        self._written = 0.0
        self._task: asyncio.Task[None] | None = None

    def callback(self, done: int, total: int) -> None:
        """Runs in the engine thread."""
        if self.cancel_requested.is_set():
            raise GenerationCancelled
        if time.monotonic() > self.deadline:
            raise GenerationTimeout
        self._latest = min(1.0, done / total) if total else 0.0

    async def flush(self) -> None:
        latest = self._latest
        if latest == self._written:
            return
        async with self.sessionmaker() as session:
            await session.execute(
                update(Job)
                .where(Job.id == self.job_id, Job.status == JobStatus.RUNNING)
                .values(progress=latest)
            )
            await session.commit()
        self._written = latest
        await notify_job_changed(self.redis, self.job_id)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval_s)
            try:
                await self.flush()
                if await self.redis.exists(job_cancel_key(self.job_id)):
                    self.cancel_requested.set()
            except Exception:
                # Progress is best effort; the job itself must keep going.
                log.exception("progress update failed for job %s", self.job_id)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop pumping; also makes a still-running engine thread stop at its next step."""
        self.cancel_requested.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
