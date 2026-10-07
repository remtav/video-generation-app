"""The worker's heartbeat, as published to Redis and read back by the API."""

import json
import time
from typing import Any, Literal

from pydantic import BaseModel
from redis.asyncio import Redis

from vidgen.keys import WORKER_HEARTBEAT_KEY

WorkerState = Literal["loading", "ready"]


class WorkerStatus(BaseModel):
    online: bool
    state: WorkerState | None = None
    engine: str | None = None
    capabilities: list[str] = []
    device: str | None = None
    last_seen: float | None = None


def heartbeat_payload(
    *, engine: str, capabilities: frozenset[str], device: str, state: WorkerState
) -> str:
    return json.dumps(
        {
            "engine": engine,
            "capabilities": sorted(capabilities),
            "device": device,
            "state": state,
            "ts": time.time(),
        }
    )


async def read_worker_status(redis: Redis) -> WorkerStatus:
    """Raises redis errors to the caller; returns online=False if there is no heartbeat."""
    raw = await redis.get(WORKER_HEARTBEAT_KEY)
    if not raw:
        return WorkerStatus(online=False)
    beat: dict[str, Any] = json.loads(raw)
    return WorkerStatus(
        online=True,
        state=beat.get("state"),
        engine=beat.get("engine"),
        capabilities=beat.get("capabilities", []),
        device=beat.get("device"),
        last_seen=beat.get("ts"),
    )
