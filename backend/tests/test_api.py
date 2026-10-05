from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from tests.conftest import DATABASE_URL, REDIS_URL, requires_services
from vidgen.api.main import create_app
from vidgen.config import get_settings


@pytest.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("VIDGEN_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c
    get_settings.cache_clear()


async def test_liveness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_degraded_without_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDGEN_DATABASE_URL", "postgresql+asyncpg://x:x@127.0.0.1:1/x")
    monkeypatch.setenv("VIDGEN_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("VIDGEN_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        resp = await c.get("/api/health")
    get_settings.cache_clear()
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["database"] is False
    assert body["redis"] is False
    assert body["storage"] is True
    assert body["worker"]["online"] is False


@requires_services
async def test_health_ok_and_reports_worker(client: httpx.AsyncClient) -> None:
    from redis.asyncio import Redis

    from vidgen.keys import WORKER_HEARTBEAT_KEY
    from vidgen.worker.engines.fake import FakeEngine
    from vidgen.worker.main import heartbeat_payload

    assert DATABASE_URL and REDIS_URL
    redis = Redis.from_url(REDIS_URL)
    await redis.set(WORKER_HEARTBEAT_KEY, heartbeat_payload(FakeEngine(), "cpu"), ex=30)
    try:
        resp = await client.get("/api/health")
    finally:
        await redis.delete(WORKER_HEARTBEAT_KEY)
        await redis.aclose()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["worker"] == {
        "online": True,
        "engine": "fake",
        "capabilities": ["i2v", "t2v"],
        "device": "cpu",
        "last_seen": body["worker"]["last_seen"],
    }
