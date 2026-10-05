from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from vidgen import __version__
from vidgen.api.routes import health
from vidgen.config import get_settings
from vidgen.db.session import make_engine
from vidgen.storage import LocalStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.db_engine = make_engine(settings.database_url)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.storage = LocalStorage(settings.storage_dir)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="vidgen", version=__version__, lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
