"""Async SQLAlchemy engine + session factory (mirrors chat-service)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from worker_service.config import WorkerSettings


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def get_sessionmaker(settings: WorkerSettings) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(settings.database_url),
        expire_on_commit=False,
        class_=AsyncSession,
    )
