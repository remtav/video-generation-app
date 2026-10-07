"""Job API against real Postgres and Redis."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from arq.connections import ArqRedis
from arq.jobs import Job as ArqJob
from arq.jobs import JobStatus as ArqJobStatus
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import DATABASE_URL, REDIS_URL, requires_services
from vidgen.db.models import Asset, AssetKind, Job, JobStatus
from vidgen.db.session import make_engine, make_sessionmaker
from vidgen.jobs import notify_job_changed, thumbnail_key, video_key
from vidgen.keys import job_cancel_key
from vidgen.presets import DEFAULT_NEGATIVE_PROMPT, PRESETS

pytestmark = [requires_services, pytest.mark.usefixtures("clean_services")]


@pytest.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert DATABASE_URL
    engine = make_engine(DATABASE_URL)
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    assert REDIS_URL
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


async def create(client: httpx.AsyncClient, **body: Any) -> dict[str, Any]:
    resp = await client.post("/api/jobs", json={"prompt": "a fox in the snow", **body})
    assert resp.status_code == 201, resp.text
    job: dict[str, Any] = resp.json()
    return job


async def set_status(
    sessionmaker: async_sessionmaker[AsyncSession], job_id: str, status: JobStatus, **values: Any
) -> None:
    async with sessionmaker() as session:
        await session.execute(
            update(Job).where(Job.id == uuid.UUID(job_id)).values(status=status, **values)
        )
        await session.commit()


async def test_presets(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/presets")
    assert resp.status_code == 200
    presets = {p["name"]: p for p in resp.json()}
    assert set(presets) == {"draft", "standard"}
    assert presets["standard"]["width"] == 1280
    assert presets["standard"]["height"] == 704
    assert presets["standard"]["num_frames"] == 121
    assert presets["draft"]["est_seconds"] < presets["standard"]["est_seconds"]


async def test_create_job_resolves_preset_and_enqueues(client: httpx.AsyncClient) -> None:
    job = await create(client, prompt="  a fox in the snow  ")
    assert job["status"] == "queued"
    assert job["mode"] == "t2v"
    assert job["prompt"] == "a fox in the snow"
    assert job["queue_position"] == 0
    assert job["video_url"] is None
    params = job["params"]
    assert params["preset"] == "draft"
    assert (params["width"], params["height"], params["num_frames"]) == (1280, 704, 49)
    assert params["steps"] == 20
    assert params["guidance_scale"] == 5.0
    assert params["negative_prompt"] == DEFAULT_NEGATIVE_PROMPT
    assert 0 <= params["seed"] < 2**32
    assert job["est_seconds"] == PRESETS["draft"].est_seconds()

    assert REDIS_URL
    arq = ArqRedis.from_url(REDIS_URL)
    try:
        assert await ArqJob(job["id"], arq).status() is ArqJobStatus.queued
    finally:
        await arq.aclose()


async def test_create_job_overrides_and_portrait(client: httpx.AsyncClient) -> None:
    job = await create(
        client,
        preset="standard",
        aspect_ratio="9:16",
        seed=123,
        steps=12,
        guidance_scale=3.5,
        negative_prompt="",
    )
    params = job["params"]
    assert (params["width"], params["height"]) == (704, 1280)
    assert params["seed"] == 123
    assert params["steps"] == 12
    assert params["guidance_scale"] == 3.5
    # The estimate follows the chosen step count.
    assert job["est_seconds"] == PRESETS["standard"].est_seconds(12)
    assert job["est_seconds"] < PRESETS["standard"].est_seconds()
    # An explicitly empty negative prompt is respected (not replaced by the default).
    assert params["negative_prompt"] == ""


@pytest.mark.parametrize(
    "body",
    [
        {"prompt": "   "},
        {"prompt": ""},
        {"prompt": "x" * 2001},
        {"prompt": "ok", "preset": "ultra"},
        {"prompt": "ok", "aspect_ratio": "1:1"},
        {"prompt": "ok", "steps": 0},
        {"prompt": "ok", "steps": 61},
        {"prompt": "ok", "seed": -1},
        {"prompt": "ok", "seed": 2**32},
        {"prompt": "ok", "guidance_scale": 0.5},
        {"prompt": "ok", "guidance_scale": 11},
    ],
)
async def test_create_job_validation(client: httpx.AsyncClient, body: dict[str, Any]) -> None:
    resp = await client.post("/api/jobs", json=body)
    assert resp.status_code == 422, resp.text


async def test_queue_positions(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    first, second, third = [await create(client) for _ in range(3)]
    positions = [(await client.get(f"/api/jobs/{j['id']}")).json() for j in (first, second, third)]
    assert [p["queue_position"] for p in positions] == [0, 1, 2]

    await set_status(sessionmaker, first["id"], JobStatus.RUNNING)
    running = (await client.get(f"/api/jobs/{first['id']}")).json()
    assert running["queue_position"] is None
    # The running job still counts as ahead of the queued ones.
    assert (await client.get(f"/api/jobs/{third['id']}")).json()["queue_position"] == 2

    await set_status(sessionmaker, first["id"], JobStatus.SUCCEEDED)
    assert (await client.get(f"/api/jobs/{second['id']}")).json()["queue_position"] == 0


async def test_list_jobs_paginates_newest_first(client: httpx.AsyncClient) -> None:
    ids = [(await create(client, prompt=f"prompt {i}"))["id"] for i in range(3)]
    page = (await client.get("/api/jobs", params={"limit": 2})).json()
    assert [j["id"] for j in page["items"]] == [ids[2], ids[1]]
    assert page["next_cursor"] is not None

    rest = (
        await client.get("/api/jobs", params={"limit": 2, "before": page["next_cursor"]})
    ).json()
    assert [j["id"] for j in rest["items"]] == [ids[0]]
    assert rest["next_cursor"] is None


async def test_unknown_job_is_404(client: httpx.AsyncClient) -> None:
    missing = uuid.uuid4()
    for method, path in [
        ("GET", f"/api/jobs/{missing}"),
        ("POST", f"/api/jobs/{missing}/cancel"),
        ("DELETE", f"/api/jobs/{missing}"),
        ("GET", f"/api/jobs/{missing}/video"),
        ("GET", f"/api/jobs/{missing}/events"),
    ]:
        resp = await client.request(method, path)
        assert resp.status_code == 404, (method, path, resp.status_code)
    assert (await client.get("/api/jobs/not-a-uuid")).status_code == 422


async def test_cancel_queued_job(client: httpx.AsyncClient) -> None:
    job = await create(client)
    resp = await client.post(f"/api/jobs/{job['id']}/cancel")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None

    again = await client.post(f"/api/jobs/{job['id']}/cancel")
    assert again.status_code == 409


async def test_cancel_running_job_sets_flag_for_worker(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    job = await create(client)
    await set_status(sessionmaker, job["id"], JobStatus.RUNNING)
    resp = await client.post(f"/api/jobs/{job['id']}/cancel")
    assert resp.status_code == 202
    assert resp.json()["status"] == "running"
    assert await redis.get(job_cancel_key(job["id"])) == "1"


async def test_delete_job(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], storage_dir: Path
) -> None:
    job = await create(client)
    assert (await client.delete(f"/api/jobs/{job['id']}")).status_code == 409

    await set_status(sessionmaker, job["id"], JobStatus.FAILED)
    job_dir = storage_dir / "jobs" / job["id"]
    job_dir.mkdir(parents=True)
    (job_dir / "video.mp4").write_bytes(b"x")

    assert (await client.delete(f"/api/jobs/{job['id']}")).status_code == 204
    assert not job_dir.exists()
    assert (await client.get(f"/api/jobs/{job['id']}")).status_code == 404


async def add_media(
    sessionmaker: async_sessionmaker[AsyncSession], storage_dir: Path, job_id: str
) -> bytes:
    jid = uuid.UUID(job_id)
    video = bytes(range(256)) * 8
    for kind, key, content_type, data in [
        (AssetKind.VIDEO, video_key(jid), "video/mp4", video),
        (AssetKind.THUMBNAIL, thumbnail_key(jid), "image/jpeg", b"jpeg"),
    ]:
        path = storage_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        async with sessionmaker() as session:
            session.add(
                Asset(
                    job_id=jid,
                    kind=kind,
                    storage_key=key,
                    content_type=content_type,
                    size_bytes=len(data),
                    meta={},
                )
            )
            await session.commit()
    await set_status(sessionmaker, job_id, JobStatus.SUCCEEDED, progress=1.0)
    return video


async def test_media_endpoints_support_ranges_and_download(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], storage_dir: Path
) -> None:
    job = await create(client)
    assert (await client.get(f"/api/jobs/{job['id']}/video")).status_code == 404
    video = await add_media(sessionmaker, storage_dir, job["id"])

    body = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert body["video_url"] == f"/api/jobs/{job['id']}/video"
    assert body["thumbnail_url"] == f"/api/jobs/{job['id']}/thumbnail"

    full = await client.get(body["video_url"])
    assert full.status_code == 200
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["accept-ranges"] == "bytes"
    assert "content-disposition" not in full.headers
    assert full.content == video

    # Browsers seek with Range requests.
    part = await client.get(body["video_url"], headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 100-199/{len(video)}"
    assert part.content == video[100:200]

    download = await client.get(body["video_url"], params={"download": "true"})
    assert download.headers["content-disposition"].startswith("attachment;")
    assert f"vidgen-{job['id'][:8]}.mp4" in download.headers["content-disposition"]

    thumb = await client.get(body["thumbnail_url"])
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"


def parse_sse(text: str) -> list[dict[str, Any]]:
    events = []
    for block in text.split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if line and not line.startswith(":")
        )
        if fields.get("event") == "job":
            events.append(json.loads(fields["data"]))
    return events


async def test_events_stream_follows_job_to_completion(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    job = await create(client)

    async def fake_worker() -> None:
        await asyncio.sleep(0.3)
        await set_status(sessionmaker, job["id"], JobStatus.RUNNING, progress=0.5)
        await notify_job_changed(redis, job["id"])
        await asyncio.sleep(0.3)
        await set_status(sessionmaker, job["id"], JobStatus.SUCCEEDED, progress=1.0)
        await notify_job_changed(redis, job["id"])

    worker = asyncio.create_task(fake_worker())
    resp = await asyncio.wait_for(client.get(f"/api/jobs/{job['id']}/events"), timeout=10)
    await worker

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "no-transform" in resp.headers["cache-control"]
    assert resp.text.startswith("retry: ")
    events = parse_sse(resp.text)
    assert [(e["status"], e["progress"]) for e in events] == [
        ("queued", 0.0),
        ("running", 0.5),
        ("succeeded", 1.0),
    ]


async def test_events_stream_of_finished_job_sends_one_event(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    job = await create(client)
    await set_status(sessionmaker, job["id"], JobStatus.CANCELLED)
    resp = await asyncio.wait_for(client.get(f"/api/jobs/{job['id']}/events"), timeout=5)
    assert [e["status"] for e in parse_sse(resp.text)] == ["cancelled"]
