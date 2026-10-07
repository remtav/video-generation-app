import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from vidgen.config import get_settings

DATABASE_URL = os.environ.get("VIDGEN_DATABASE_URL")
REDIS_URL = os.environ.get("VIDGEN_REDIS_URL")

# Integration tests TRUNCATE the jobs tables and FLUSHDB the Redis database: point these
# variables at a disposable database (as CI does), never at real data.
requires_services = pytest.mark.skipif(
    not (DATABASE_URL and REDIS_URL),
    reason="set VIDGEN_DATABASE_URL and VIDGEN_REDIS_URL to run integration tests",
)


@pytest.fixture
async def clean_services() -> AsyncIterator[None]:
    """Empty the jobs tables and the Redis database before a test."""
    from redis.asyncio import Redis
    from sqlalchemy import text

    from vidgen.db.session import make_engine

    assert DATABASE_URL and REDIS_URL
    engine = make_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE jobs, assets"))
    await engine.dispose()
    redis = Redis.from_url(REDIS_URL)
    await redis.flushdb()
    await redis.aclose()
    yield


@pytest.fixture
def storage_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("VIDGEN_STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    yield tmp_path / "storage"
    get_settings.cache_clear()


@pytest.fixture
async def client(storage_dir: Path) -> AsyncIterator[httpx.AsyncClient]:
    from vidgen.api.main import create_app

    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c
