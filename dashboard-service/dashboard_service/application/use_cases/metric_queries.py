"""Dashboard metric use cases (PRD §7.8).

Each use case takes a :class:`WindowKey`, resolves the bounds, and
delegates to the injected :class:`MetricsReader`. The handlers don't
talk to ClickHouse directly — that lives in the infrastructure
adapter — so unit tests can exercise the routing with a fake reader.
"""

from __future__ import annotations

from dataclasses import dataclass

from dashboard_service.application.ports.metrics_reader import (
    LatencyPercentiles,
    MetricsReader,
    ProviderCost,
)
from dashboard_service.domain.window import WindowKey, window_bounds


@dataclass(frozen=True, slots=True)
class LatencyResult:
    window: WindowKey
    p50: float
    p95: float
    p99: float


@dataclass(frozen=True, slots=True)
class ThroughputResult:
    window: WindowKey
    request_count: int


@dataclass(frozen=True, slots=True)
class ErrorRateResult:
    window: WindowKey
    error_rate: float


@dataclass(frozen=True, slots=True)
class ProviderCostRow:
    provider: str
    cost_usd: float


@dataclass(frozen=True, slots=True)
class CostResult:
    window: WindowKey
    breakdown: list[ProviderCostRow]


class LatencyPercentilesHandler:
    def __init__(self, *, reader: MetricsReader) -> None:
        self._reader = reader

    async def handle(self, window: WindowKey) -> LatencyResult:
        since, until = window_bounds(window)
        result: LatencyPercentiles = await self._reader.latency_percentiles(
            since=since, until=until
        )
        return LatencyResult(window=window, p50=result.p50, p95=result.p95, p99=result.p99)


class ThroughputHandler:
    def __init__(self, *, reader: MetricsReader) -> None:
        self._reader = reader

    async def handle(self, window: WindowKey) -> ThroughputResult:
        since, until = window_bounds(window)
        count = await self._reader.throughput(since=since, until=until)
        return ThroughputResult(window=window, request_count=count)


class ErrorRateHandler:
    def __init__(self, *, reader: MetricsReader) -> None:
        self._reader = reader

    async def handle(self, window: WindowKey) -> ErrorRateResult:
        since, until = window_bounds(window)
        rate = await self._reader.error_rate(since=since, until=until)
        return ErrorRateResult(window=window, error_rate=rate)


class CostHandler:
    def __init__(self, *, reader: MetricsReader) -> None:
        self._reader = reader

    async def handle(self, window: WindowKey) -> CostResult:
        since, until = window_bounds(window)
        rows: list[ProviderCost] = await self._reader.cost_by_provider(since=since, until=until)
        return CostResult(
            window=window,
            breakdown=[ProviderCostRow(provider=r.provider, cost_usd=r.cost_usd) for r in rows],
        )
