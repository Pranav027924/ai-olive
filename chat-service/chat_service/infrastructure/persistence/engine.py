"""Async SQLAlchemy engine + session factory.

A single engine is created per process (module-level via
``get_engine``) and reused. ``get_sessionmaker`` returns the factory
that the repository uses to open per-call sessions.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chat_service.config import ChatServiceSettings


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def get_sessionmaker(settings: ChatServiceSettings) -> async_sessionmaker[AsyncSession]:
    engine = get_engine(settings.database_url)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
