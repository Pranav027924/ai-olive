"""Fixtures for chat-service infrastructure tests.

Spins up a real Postgres via testcontainers (session-scoped — one
container per pytest run, ~5s warmup). Each test gets a fresh ``chat``
schema (dropped and recreated) so they cannot see each other's data
without paying the container-start tax per test.

These tests run in CI on every push (see .github/workflows/ci.yml in
Phase 0.6 + the per-service job that lands when more services join).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from chat_service.infrastructure.persistence.postgres_session_repo import (
    PostgresSessionRepository,
)
from chat_service.infrastructure.persistence.sqlalchemy_models import Base, UserRow
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_EMAIL = "dev@local"


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver=None) as pg:
        yield pg


def _async_url(container: PostgresContainer) -> str:
    return (
        f"postgresql+asyncpg://{container.username}:{container.password}"
        f"@{container.get_container_host_ip()}:"
        f"{container.get_exposed_port(5432)}/{container.dbname}"
    )


@pytest_asyncio.fixture
async def engine(postgres_container: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(_async_url(postgres_container), future=True)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS chat CASCADE"))
        await conn.execute(text("CREATE SCHEMA chat"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def dev_user_id(sessionmaker: async_sessionmaker[AsyncSession]) -> UUID:
    """Seed the dev user (FK target for sessions) and return its id."""
    async with sessionmaker() as db, db.begin():
        db.add(UserRow(id=DEV_USER_ID, email=DEV_USER_EMAIL))
    return DEV_USER_ID


@pytest_asyncio.fixture
async def fresh_user_id(sessionmaker: async_sessionmaker[AsyncSession]) -> UUID:
    """Create a brand-new user row and return its id (for isolation tests)."""
    uid = uuid4()
    async with sessionmaker() as db, db.begin():
        db.add(UserRow(id=uid, email=f"user-{uid}@local"))
    return uid


@pytest_asyncio.fixture
async def pg_repo(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> PostgresSessionRepository:
    return PostgresSessionRepository(sessionmaker)
