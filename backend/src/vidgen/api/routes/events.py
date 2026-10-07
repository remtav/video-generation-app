"""Server-Sent Events: live updates for one job.

The worker publishes a "changed" notification on the job's Redis channel whenever it
updates the row. This stream re-reads the row on every notification (and every couple of
seconds as a fallback, which also keeps queue positions fresh) and sends it whenever it
changed. The database stays the single source of truth.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from vidgen.api.deps import RedisDep, SessionDep
from vidgen.api.schemas import JobOut
from vidgen.db.models import Job
from vidgen.jobs import TERMINAL_STATUSES, queue_position
from vidgen.keys import job_events_channel

router = APIRouter(tags=["jobs"])

POLL_INTERVAL_S = 2.0
KEEPALIVE_INTERVAL_S = 15.0
# Tell EventSource how long to wait before reconnecting after a dropped connection.
RETRY_MS = 3000

SSE_HEADERS = {
    # no-transform keeps proxies (including Next's compression) from buffering the stream.
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


async def _snapshot(
    sessionmaker: async_sessionmaker[AsyncSession], job_id: uuid.UUID
) -> JobOut | None:
    async with sessionmaker() as session:
        job = await session.scalar(
            select(Job).where(Job.id == job_id).options(selectinload(Job.assets))
        )
        if job is None:
            return None
        return JobOut.from_job(
            job,
            queue_position=await queue_position(session, job),
            kinds={asset.kind for asset in job.assets},
        )


def _event(job: JobOut) -> str:
    return f"event: job\ndata: {json.dumps(job.model_dump(mode='json'))}\n\n"


async def job_event_stream(
    request: Request,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    job_id: uuid.UUID,
) -> AsyncIterator[str]:
    pubsub = redis.pubsub()
    # Subscribe before the first read so no notification falls between them.
    await pubsub.subscribe(job_events_channel(job_id))
    try:
        yield f"retry: {RETRY_MS}\n\n"
        last_sent: str | None = None
        last_write = time.monotonic()
        while True:
            job = await _snapshot(sessionmaker, job_id)
            if job is None:
                yield 'event: error\ndata: {"detail": "job not found"}\n\n'
                return
            event = _event(job)
            if event != last_sent:
                yield event
                last_sent, last_write = event, time.monotonic()
            if job.status in TERMINAL_STATUSES:
                return
            if time.monotonic() - last_write > KEEPALIVE_INTERVAL_S:
                yield ": keepalive\n\n"
                last_write = time.monotonic()
            # Wake on the worker's notification, or poll after a short while.
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_INTERVAL_S)
            if await request.is_disconnected():
                return
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()  # type: ignore[no-untyped-call]


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: uuid.UUID, request: Request, session: SessionDep, redis: RedisDep
) -> StreamingResponse:
    exists = await session.scalar(select(Job.id).where(Job.id == job_id))
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    await session.close()
    return StreamingResponse(
        job_event_stream(request, request.app.state.sessionmaker, redis, job_id),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
