"""Integration tests for PostgresLogRepository (Phase 5.7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from contracts.log_event import LogEvent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.infrastructure.persistence.postgres_log_repo import (
    PostgresLogRepository,
)

EventFactory = Callable[..., LogEvent]


def _processed_from(event: LogEvent, **overrides: object) -> ProcessedLog:
    pl = ProcessedLog.from_event(
        event,
        redacted_input_preview="hi",
        redacted_output_preview="hello",
        cost_usd=Decimal("0.001"),
    )
    if overrides:
        pl = replace(pl, **overrides)  # type: ignore[arg-type]
    return pl


async def test_insert_then_exists_returns_true(
    log_repo: PostgresLogRepository, event_factory: EventFactory
) -> None:
    ev = event_factory()
    await log_repo.insert(_processed_from(ev))
    assert await log_repo.exists(ev.event_id) is True


async def test_exists_returns_false_for_unknown_id(
    log_repo: PostgresLogRepository,
) -> None:
    assert await log_repo.exists(uuid4()) is False


async def test_insert_persists_every_column(
    log_repo: PostgresLogRepository,
    sessionmaker: async_sessionmaker[AsyncSession],
    event_factory: EventFactory,
) -> None:
    ev = event_factory(
        prompt_tokens=10,
        completion_tokens=20,
        ttft_ms=42,
        raw_metadata={"finish_reason": "stop"},
    )
    pl = _processed_from(ev, cost_usd=Decimal("0.001234"))
    await log_repo.insert(pl)

    async with sessionmaker() as db:
        row = await db.execute(
            text("SELECT * FROM logs.inference_logs WHERE id = :id"),
            {"id": str(ev.event_id)},
        )
        record = row.mappings().one()

    assert record["session_id"] == ev.session_id
    assert record["provider"] == "anthropic"
    assert record["model"] == "claude-opus-4-7"
    assert record["status"] == "success"
    assert record["latency_ms"] == 1000
    assert record["ttft_ms"] == 42
    assert record["prompt_tokens"] == 10
    assert record["completion_tokens"] == 20
    assert record["cost_usd"] == Decimal("0.001234")
    assert record["raw_metadata"] == {"finish_reason": "stop"}
    assert record["sdk_version"] == "0.1.0"
    assert record["ingested_at"] is not None


async def test_error_event_also_writes_log_errors_row(
    log_repo: PostgresLogRepository,
    sessionmaker: async_sessionmaker[AsyncSession],
    event_factory: EventFactory,
) -> None:
    ev = event_factory(
        status="error",
        error_type="ProviderTimeout",
        error_message="upstream 504",
        http_status=504,
        prompt_tokens=None,
        completion_tokens=None,
    )
    err_id = uuid4()
    pl = _processed_from(ev, cost_usd=None, log_errors_id=err_id)

    await log_repo.insert(pl)

    async with sessionmaker() as db:
        log_count = await db.scalar(
            text("SELECT COUNT(*) FROM logs.inference_logs WHERE id = CAST(:id AS uuid)"),
            {"id": str(ev.event_id)},
        )
        err = await db.execute(
            text("SELECT * FROM logs.log_errors WHERE id = CAST(:id AS uuid)"),
            {"id": str(err_id)},
        )
    assert log_count == 1
    err_row = err.mappings().one()
    assert err_row["log_id"] == ev.event_id
    assert err_row["error_type"] == "ProviderTimeout"
    assert err_row["error_message"] == "upstream 504"
    assert err_row["http_status"] == 504


async def test_duplicate_insert_is_silently_swallowed(
    log_repo: PostgresLogRepository,
    sessionmaker: async_sessionmaker[AsyncSession],
    event_factory: EventFactory,
) -> None:
    ev = event_factory()
    await log_repo.insert(_processed_from(ev))
    await log_repo.insert(_processed_from(ev))

    async with sessionmaker() as db:
        count = await db.scalar(
            text("SELECT COUNT(*) FROM logs.inference_logs WHERE id = CAST(:id AS uuid)"),
            {"id": str(ev.event_id)},
        )
    assert count == 1


async def test_partition_routing_works_for_recent_started_at(
    log_repo: PostgresLogRepository,
    event_factory: EventFactory,
) -> None:
    """A row with started_at inside the catchall partition should land."""
    ev = event_factory(started_at=datetime(2029, 12, 31, 23, 59, tzinfo=UTC))
    pl = _processed_from(ev)
    pl = replace(pl, started_at=ev.started_at, finished_at=ev.started_at)
    await log_repo.insert(pl)
    assert await log_repo.exists(ev.event_id) is True
