"""Redis key, channel and task names shared by the API and the worker."""

import uuid

WORKER_HEARTBEAT_KEY = "vidgen:worker:heartbeat"
GENERATE_TASK = "generate_video"


def job_events_channel(job_id: uuid.UUID | str) -> str:
    """Pub/sub channel the worker notifies whenever a job's row changes."""
    return f"vidgen:job:{job_id}:events"


def job_cancel_key(job_id: uuid.UUID | str) -> str:
    """Set by the API to ask the worker to stop a running job."""
    return f"vidgen:job:{job_id}:cancel"
