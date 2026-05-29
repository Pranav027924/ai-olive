"""Fixtures for worker-service infrastructure tests.

Spins up a real Postgres (session-scoped testcontainer) and applies the
same partitioned schema the production Alembic migration creates.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from contracts.log_event import LogEvent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from worker_service.infrastructure.persistence.postgres_log_repo import (
    PostgresLogRepository,
)

CREATE_DDL = (
    "CREATE SCHEMA IF NOT EXISTS logs;",
    """
    CREATE TABLE logs.inference_logs (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        message_id UUID,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL,
        finished_at TIMESTAMPTZ NOT NULL,
        latency_ms INT NOT NULL,
        ttft_ms INT,
        prompt_tokens INT,
        completion_tokens INT,
        input_preview TEXT,
        output_preview TEXT,
        cost_usd NUMERIC(12,6),
        raw_metadata JSONB,
        sdk_version TEXT,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (id, started_at)
    ) PARTITION BY RANGE (started_at);
    """,
    """
    CREATE TABLE logs.inference_logs_p_catchall
    PARTITION OF logs.inference_logs
    FOR VALUES FROM ('2026-01-01') TO ('2030-01-01');
    """,
    """
    CREATE TABLE logs.log_errors (
        id UUID PRIMARY KEY,
        log_id UUID NOT NULL,
        error_type TEXT NOT NULL,
        error_message TEXT,
        http_status INT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
)


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
        await conn.execute(text("DROP SCHEMA IF EXISTS logs CASCADE"))
        for stmt in CREATE_DDL:
            await conn.execute(text(stmt))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def log_repo(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> PostgresLogRepository:
    return PostgresLogRepository(sessionmaker)


# ---------------------------------------------------------------------------
# LogEvent factory shared by integration tests
# ---------------------------------------------------------------------------


EventFactory = Callable[..., LogEvent]


@pytest.fixture
def event_factory() -> EventFactory:
    """Return a callable that builds a LogEvent with sensible defaults."""

    def _make(**overrides: object) -> LogEvent:
        base: dict[str, object] = {
            "event_id": uuid4(),
            "session_id": uuid4(),
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "status": "success",
            "started_at": datetime(2026, 6, 1, tzinfo=UTC),
            "finished_at": datetime(2026, 6, 1, 0, 0, 1, tzinfo=UTC),
            "latency_ms": 1000,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "input_preview": "hi",
            "output_preview": "hello",
            "sdk_version": "0.1.0",
        }
        base.update(overrides)
        return LogEvent(**base)  # type: ignore[arg-type]

    return _make
