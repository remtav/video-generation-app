"""Liveness and readiness of the stack: database, Redis, storage and the GPU worker."""

import json
from typing import Any, Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from vidgen import __version__
from vidgen.keys import WORKER_HEARTBEAT_KEY

router = APIRouter(tags=["health"])


class WorkerStatus(BaseModel):
    online: bool
    engine: str | None = None
    capabilities: list[str] = []
    device: str | None = None
    last_seen: float | None = None


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

    worker = WorkerStatus(online=False)
    try:
        raw = await state.redis.get(WORKER_HEARTBEAT_KEY)
        redis_ok = True
    except Exception:
        raw, redis_ok = None, False
    if raw:
        beat: dict[str, Any] = json.loads(raw)
        worker = WorkerStatus(
            online=True,
            engine=beat.get("engine"),
            capabilities=beat.get("capabilities", []),
            device=beat.get("device"),
            last_seen=beat.get("ts"),
        )

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
