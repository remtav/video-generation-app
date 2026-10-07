"""Job helpers shared by the API and the worker."""

import uuid

from redis.asyncio import Redis
from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from vidgen.db.models import Job, JobStatus
from vidgen.keys import job_events_channel

TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})
ACTIVE_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


def video_key(job_id: uuid.UUID) -> str:
    return f"jobs/{job_id}/video.mp4"


def thumbnail_key(job_id: uuid.UUID) -> str:
    return f"jobs/{job_id}/thumbnail.jpg"


def job_dir_key(job_id: uuid.UUID) -> str:
    return f"jobs/{job_id}"


async def queue_position(session: AsyncSession, job: Job) -> int | None:
    """Number of jobs that will run before this one (0 = next), or None if not queued.

    The worker takes jobs in submission order, one at a time.
    """
    if job.status is not JobStatus.QUEUED:
        return None
    ahead = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            or_(
                Job.status == JobStatus.RUNNING,
                (Job.status == JobStatus.QUEUED)
                & (tuple_(Job.created_at, Job.id) < tuple_(job.created_at, job.id)),
            )
        )
    )
    return int(ahead or 0)


async def notify_job_changed(redis: Redis, job_id: uuid.UUID | str) -> None:
    """Wake up any SSE streams following this job; they re-read the row."""
    await redis.publish(job_events_channel(job_id), "changed")
