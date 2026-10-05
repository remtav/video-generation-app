"""Schema tests against a real Postgres (migrated with Alembic in CI and docker compose)."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import DATABASE_URL, requires_services
from vidgen.db.models import Asset, AssetKind, Job, JobMode, JobStatus
from vidgen.db.session import make_engine, make_sessionmaker

pytestmark = requires_services


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    assert DATABASE_URL
    engine = make_engine(DATABASE_URL)
    async with engine.connect() as conn:
        trans = await conn.begin()
        sessionmaker = make_sessionmaker(engine)
        async with sessionmaker(bind=conn) as s:
            yield s
        await trans.rollback()
    await engine.dispose()


async def test_job_defaults_and_asset_cascade(session: AsyncSession) -> None:
    job = Job(mode=JobMode.T2V, engine="fake", prompt="a cat", params={"steps": 4})
    job.assets.append(
        Asset(
            kind=AssetKind.VIDEO,
            storage_key=f"jobs/{job.id}/video.mp4",
            content_type="video/mp4",
            size_bytes=123,
            meta={"fps": 24},
        )
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)

    assert job.status is JobStatus.QUEUED
    assert job.progress == 0.0
    assert job.created_at is not None

    await session.delete(job)
    await session.flush()
    assert (await session.execute(select(Asset))).scalars().all() == []
