"""Tests for ClickHouseMetricsReader (Phase 7.10).

Uses a fake aiochclient that records the SQL it was handed and
returns hand-built rows so we exercise the query/row shaping
without standing up a real ClickHouse instance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dashboard_service.infrastructure.clickhouse.clickhouse_metrics_reader import (
    ClickHouseMetricsReader,
)


class _FakeClient:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.fetch_calls: list[str] = []
        self.fetchrow_calls: list[str] = []

    async def fetchrow(self, query: str) -> dict[str, Any] | None:
        self.fetchrow_calls.append(query)
        return self.row

    async def fetch(self, query: str) -> list[dict[str, Any]]:
        self.fetch_calls.append(query)
        return self.rows


SINCE = datetime(2026, 6, 1, tzinfo=UTC)
UNTIL = datetime(2026, 6, 2, tzinfo=UTC)


async def test_latency_percentiles_query_shape() -> None:
    client = _FakeClient(row={"p50": 100.0, "p95": 250.0, "p99": 500.0})
    reader = ClickHouseMetricsReader(client=client)

    result = await reader.latency_percentiles(since=SINCE, until=UNTIL)

    assert result.p50 == 100.0
    assert result.p95 == 250.0
    assert result.p99 == 500.0
    query = client.fetchrow_calls[0]
    assert "quantile(0.5)" in query
    assert "quantile(0.95)" in query
    assert "quantile(0.99)" in query
    # Window bounds are inlined as quoted naive-UTC literals.
    assert "started_at >= '2026-06-01 00:00:00" in query
    assert "started_at < '2026-06-02 00:00:00" in query


async def test_latency_percentiles_empty_table_returns_zeroes() -> None:
    reader = ClickHouseMetricsReader(
        client=_FakeClient(row={"p50": None, "p95": None, "p99": None})
    )

    result = await reader.latency_percentiles(since=SINCE, until=UNTIL)

    assert (result.p50, result.p95, result.p99) == (0.0, 0.0, 0.0)


async def test_throughput_returns_count_from_row() -> None:
    reader = ClickHouseMetricsReader(client=_FakeClient(row={"n": 42}))

    assert await reader.throughput(since=SINCE, until=UNTIL) == 42


async def test_throughput_handles_missing_row_gracefully() -> None:
    reader = ClickHouseMetricsReader(client=_FakeClient(row=None))

    assert await reader.throughput(since=SINCE, until=UNTIL) == 0


async def test_error_rate_divides_errors_by_total() -> None:
    reader = ClickHouseMetricsReader(client=_FakeClient(row={"e": 3, "n": 12}))

    assert await reader.error_rate(since=SINCE, until=UNTIL) == 0.25


async def test_error_rate_zero_total_returns_zero() -> None:
    reader = ClickHouseMetricsReader(client=_FakeClient(row={"e": 0, "n": 0}))

    assert await reader.error_rate(since=SINCE, until=UNTIL) == 0.0


async def test_cost_by_provider_maps_rows_into_value_objects() -> None:
    client = _FakeClient(
        rows=[
            {"provider": "openai", "total": 12.34},
            {"provider": "anthropic", "total": 1.23},
        ]
    )
    reader = ClickHouseMetricsReader(client=client)

    rows = await reader.cost_by_provider(since=SINCE, until=UNTIL)

    assert [(r.provider, r.cost_usd) for r in rows] == [
        ("openai", 12.34),
        ("anthropic", 1.23),
    ]
    query = client.fetch_calls[0]
    assert "GROUP BY provider" in query
    assert "ORDER BY total DESC" in query


async def test_custom_table_name_is_honoured_in_queries() -> None:
    client = _FakeClient(row={"n": 0})
    reader = ClickHouseMetricsReader(client=client, table="weird_table")

    await reader.throughput(since=SINCE, until=UNTIL)

    query = client.fetchrow_calls[0]
    assert "FROM weird_table" in query
