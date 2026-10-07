import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq.connections import ArqRedis
from fastapi import FastAPI
from redis.asyncio import Redis

from vidgen import __version__
from vidgen.api.routes import events, health, jobs, presets
from vidgen.config import get_settings
from vidgen.db.session import make_engine, make_sessionmaker
from vidgen.storage import LocalStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    settings = get_settings()
    app.state.db_engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.db_engine)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # Connects lazily, so the API starts (and reports degraded health) without Redis.
    app.state.arq = ArqRedis.from_url(settings.redis_url)
    app.state.storage = LocalStorage(settings.storage_dir)
    try:
        yield
    finally:
        await app.state.arq.aclose()
        await app.state.redis.aclose()
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="vidgen", version=__version__, lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(presets.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    return app


app = create_app()
