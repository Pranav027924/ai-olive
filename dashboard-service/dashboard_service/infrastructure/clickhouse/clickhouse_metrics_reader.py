# ruff: noqa: S608 — table name comes from settings, not user input
"""ClickHouseMetricsReader — read-only adapter for inference_metrics (PRD §7.10).

Issues parameterised SELECTs via aiochclient and shapes the rows
into the value objects the application layer expects. Errors from
the HTTP layer propagate as-is; the interfaces layer maps them to
HTTP 503.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dashboard_service.application.ports.metrics_reader import (
    LatencyPercentiles,
    MetricsReader,
    ProviderCost,
)


@dataclass(frozen=True, slots=True)
class _LatencyRow(LatencyPercentiles):
    p50: float
    p95: float
    p99: float


@dataclass(frozen=True, slots=True)
class _ProviderCostRow(ProviderCost):
    provider: str
    cost_usd: float


class ClickHouseMetricsReader(MetricsReader):
    def __init__(self, *, client: Any, table: str = "inference_metrics") -> None:
        self._client = client
        self._table = table

    async def latency_percentiles(self, *, since: datetime, until: datetime) -> LatencyPercentiles:
        query = (
            f"SELECT quantile(0.5)(latency_ms) AS p50, "
            f"quantile(0.95)(latency_ms) AS p95, "
            f"quantile(0.99)(latency_ms) AS p99 "
            f"FROM {self._table} "
            f"WHERE started_at >= {{since:DateTime64}} "
            f"AND started_at < {{until:DateTime64}}"
        )
        row = await self._client.fetchrow(query, params={"since": since, "until": until})
        if row is None:
            return _LatencyRow(p50=0.0, p95=0.0, p99=0.0)
        return _LatencyRow(
            p50=float(row["p50"] or 0.0),
            p95=float(row["p95"] or 0.0),
            p99=float(row["p99"] or 0.0),
        )

    async def throughput(self, *, since: datetime, until: datetime) -> int:
        query = (
            f"SELECT count() AS n FROM {self._table} "
            f"WHERE started_at >= {{since:DateTime64}} "
            f"AND started_at < {{until:DateTime64}}"
        )
        row = await self._client.fetchrow(query, params={"since": since, "until": until})
        return int(row["n"]) if row is not None else 0

    async def error_rate(self, *, since: datetime, until: datetime) -> float:
        query = (
            f"SELECT countIf(status = 'error') AS e, count() AS n FROM {self._table} "
            f"WHERE started_at >= {{since:DateTime64}} "
            f"AND started_at < {{until:DateTime64}}"
        )
        row = await self._client.fetchrow(query, params={"since": since, "until": until})
        if row is None or not row["n"]:
            return 0.0
        return float(row["e"]) / float(row["n"])

    async def cost_by_provider(self, *, since: datetime, until: datetime) -> list[ProviderCost]:
        query = (
            f"SELECT provider, sum(cost_usd) AS total FROM {self._table} "
            f"WHERE started_at >= {{since:DateTime64}} "
            f"AND started_at < {{until:DateTime64}} "
            f"GROUP BY provider ORDER BY total DESC"
        )
        rows = await self._client.fetch(query, params={"since": since, "until": until})
        return [
            _ProviderCostRow(provider=str(r["provider"]), cost_usd=float(r["total"])) for r in rows
        ]
