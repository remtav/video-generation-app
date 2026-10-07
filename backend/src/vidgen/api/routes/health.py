"""Liveness and readiness of the stack: database, Redis, storage and the GPU worker."""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from vidgen import __version__
from vidgen.worker_status import WorkerStatus, read_worker_status

router = APIRouter(tags=["health"])


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: bool
    redis: bool
    storage: bool
    worker: WorkerStatus


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health", response_model=HealthReport)
async def readiness(request: Request, response: Response) -> HealthReport:
    state = request.app.state

    try:
        async with state.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False

    try:
        worker = await read_worker_status(state.redis)
        redis_ok = True
    except Exception:
        worker, redis_ok = WorkerStatus(online=False), False

    storage = state.storage.is_writable()
    # The worker being offline does not make the API unhealthy; it is reported separately.
    healthy = database and redis_ok and storage
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthReport(
        status="ok" if healthy else "degraded",
        version=__version__,
        database=database,
        redis=redis_ok,
        storage=storage,
        worker=worker,
    )
