from collections.abc import AsyncIterator
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from vidgen.config import Settings, get_settings
from vidgen.storage import LocalStorage


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def get_arq(request: Request) -> ArqRedis:
    arq: ArqRedis = request.app.state.arq
    return arq


def get_storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
ArqDep = Annotated[ArqRedis, Depends(get_arq)]
StorageDep = Annotated[LocalStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
