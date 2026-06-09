"""Tests for ClickHouseMetricsSink (Phase 7.6).

The aiochclient HTTP layer is replaced with a small in-memory fake
so the test runs without ClickHouse being up.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.infrastructure.clickhouse.clickhouse_metrics_sink import (
    INSERT_SQL,
    ClickHouseMetricsSink,
)


class _FakeClient:
    def __init__(self, *, raise_on_execute: int = 0) -> None:
        self.executes: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False
        self._raise_on_execute = raise_on_execute

    async def execute(self, query: str, *rows: Any) -> None:
        if self._raise_on_execute > 0:
            self._raise_on_execute -= 1
            raise RuntimeError("clickhouse unavailable")
        self.executes.append((query, rows))

    async def close(self) -> None:
        self.closed = True


def _processed(event_id: object | None = None) -> ProcessedLog:
    return ProcessedLog(
        id=event_id or uuid4(),  # type: ignore[arg-type]
        session_id=uuid4(),
        message_id=None,
        provider="anthropic",
        model="claude-opus-4-7",
        status="success",
        started_at=datetime(2026, 6, 1, tzinfo=UTC),
        finished_at=datetime(2026, 6, 1, 0, 0, 1, tzinfo=UTC),
        latency_ms=1000,
        ttft_ms=120,
        prompt_tokens=10,
        completion_tokens=20,
        input_preview="hi",
        output_preview="hello",
        cost_usd=Decimal("0.000123"),
        raw_metadata={},
        sdk_version="0.1.0",
    )


# ---------------------------------------------------------------------------
# Buffer behaviour
# ---------------------------------------------------------------------------


async def test_record_below_buffer_threshold_does_not_flush() -> None:
    client = _FakeClient()
    sink = ClickHouseMetricsSink(client=client, buffer_size=5, flush_interval_seconds=3600)

    await sink.record(_processed())
    await sink.record(_processed())

    assert client.executes == []


async def test_record_at_buffer_threshold_flushes() -> None:
    client = _FakeClient()
    sink = ClickHouseMetricsSink(client=client, buffer_size=2, flush_interval_seconds=3600)

    await sink.record(_processed())
    await sink.record(_processed())

    assert len(client.executes) == 1
    query, rows = client.executes[0]
    assert query == INSERT_SQL
    assert len(rows) == 2


async def test_explicit_flush_drains_buffer() -> None:
    client = _FakeClient()
    sink = ClickHouseMetricsSink(client=client, buffer_size=100, flush_interval_seconds=3600)
    await sink.record(_processed())
    await sink.record(_processed())

    await sink.flush()

    assert len(client.executes) == 1
    assert len(client.executes[0][1]) == 2


async def test_flush_on_empty_buffer_is_a_noop() -> None:
    client = _FakeClient()
    sink = ClickHouseMetricsSink(client=client, buffer_size=10, flush_interval_seconds=3600)

    await sink.flush()

    assert client.executes == []


# ---------------------------------------------------------------------------
# Failure semantics
# ---------------------------------------------------------------------------


async def test_flush_failure_requeues_batch_for_next_attempt() -> None:
    """An exception during execute() must not lose the rows — they
    get put back at the head of the buffer so the next flush retries."""
    client = _FakeClient(raise_on_execute=1)
    sink = ClickHouseMetricsSink(client=client, buffer_size=2, flush_interval_seconds=3600)
    a, b = _processed(), _processed()

    await sink.record(a)
    await sink.record(b)  # triggers flush -> raises; rows requeued
    await sink.flush()  # retries successfully

    assert len(client.executes) == 1
    _, rows = client.executes[0]
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Row encoding
# ---------------------------------------------------------------------------


async def test_row_carries_all_dashboard_columns() -> None:
    client = _FakeClient()
    sink = ClickHouseMetricsSink(client=client, buffer_size=1, flush_interval_seconds=3600)
    processed = _processed()

    await sink.record(processed)

    _, rows = client.executes[0]
    row = rows[0]
    assert row[0] == processed.id
    assert row[1] == processed.session_id
    assert row[2] == processed.provider
    assert row[3] == processed.model
    assert row[4] == processed.status
    assert row[5] == processed.started_at
    assert row[6] == processed.finished_at
    assert row[7] == processed.latency_ms
    assert row[8] == processed.ttft_ms
    assert row[9] == processed.prompt_tokens
    assert row[10] == processed.completion_tokens
    assert row[11] == pytest.approx(float(processed.cost_usd))  # type: ignore[arg-type]


async def test_close_flushes_then_closes_underlying_client() -> None:
    client = _FakeClient()
    sink = ClickHouseMetricsSink(client=client, buffer_size=100, flush_interval_seconds=3600)
    await sink.record(_processed())

    await sink.close()

    assert len(client.executes) == 1
    assert client.closed is True


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_buffer_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="buffer_size"):
        ClickHouseMetricsSink(client=_FakeClient(), buffer_size=0)


def test_flush_interval_must_be_positive() -> None:
    with pytest.raises(ValueError, match="flush_interval"):
        ClickHouseMetricsSink(client=_FakeClient(), flush_interval_seconds=0)
