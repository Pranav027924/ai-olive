"""Tests for the dashboard metric use cases (Phase 7.9)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dashboard_service.application.ports.metrics_reader import (
    LatencyPercentiles,
    ProviderCost,
)
from dashboard_service.application.use_cases.metric_queries import (
    CostHandler,
    ErrorRateHandler,
    LatencyPercentilesHandler,
    ProviderCostRow,
    ThroughputHandler,
)
from dashboard_service.domain.window import WindowKey


@dataclass
class _Lat:
    p50: float
    p95: float
    p99: float


@dataclass
class _PC:
    provider: str
    cost_usd: float


class _FakeReader:
    def __init__(
        self,
        *,
        latency: LatencyPercentiles | None = None,
        throughput_value: int = 0,
        error_rate_value: float = 0.0,
        costs: list[ProviderCost] | None = None,
    ) -> None:
        self._latency = latency or _Lat(p50=0.0, p95=0.0, p99=0.0)
        self._throughput = throughput_value
        self._error_rate = error_rate_value
        self._costs = costs or []
        self.calls: list[tuple[str, datetime, datetime]] = []

    async def latency_percentiles(self, *, since: datetime, until: datetime) -> LatencyPercentiles:
        self.calls.append(("latency", since, until))
        return self._latency

    async def throughput(self, *, since: datetime, until: datetime) -> int:
        self.calls.append(("throughput", since, until))
        return self._throughput

    async def error_rate(self, *, since: datetime, until: datetime) -> float:
        self.calls.append(("error_rate", since, until))
        return self._error_rate

    async def cost_by_provider(self, *, since: datetime, until: datetime) -> list[ProviderCost]:
        self.calls.append(("cost", since, until))
        return list(self._costs)


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


async def test_latency_percentiles_forwarded_with_window_bounds() -> None:
    reader = _FakeReader(latency=_Lat(p50=120.0, p95=300.0, p99=900.0))
    handler = LatencyPercentilesHandler(reader=reader)

    result = await handler.handle(WindowKey.LAST_HOUR)

    assert result.p50 == 120.0
    assert result.p95 == 300.0
    assert result.p99 == 900.0
    assert result.window is WindowKey.LAST_HOUR
    name, since, until = reader.calls[0]
    assert name == "latency"
    assert (until - since).total_seconds() == 3600


# ---------------------------------------------------------------------------
# Throughput
# ---------------------------------------------------------------------------


async def test_throughput_handler_returns_reader_count() -> None:
    reader = _FakeReader(throughput_value=42)
    handler = ThroughputHandler(reader=reader)

    result = await handler.handle(WindowKey.LAST_24_HOURS)

    assert result.request_count == 42
    assert result.window is WindowKey.LAST_24_HOURS


async def test_throughput_handler_widens_window_for_24h() -> None:
    reader = _FakeReader()
    handler = ThroughputHandler(reader=reader)

    await handler.handle(WindowKey.LAST_24_HOURS)

    _, since, until = reader.calls[0]
    assert (until - since).total_seconds() == 24 * 3600


# ---------------------------------------------------------------------------
# Error rate
# ---------------------------------------------------------------------------


async def test_error_rate_handler_returns_reader_value() -> None:
    reader = _FakeReader(error_rate_value=0.125)
    handler = ErrorRateHandler(reader=reader)

    result = await handler.handle(WindowKey.LAST_7_DAYS)

    assert result.error_rate == 0.125


async def test_error_rate_handler_widens_window_for_7d() -> None:
    reader = _FakeReader()
    handler = ErrorRateHandler(reader=reader)

    await handler.handle(WindowKey.LAST_7_DAYS)

    _, since, until = reader.calls[0]
    assert (until - since).days == 7


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


async def test_cost_handler_returns_breakdown_in_reader_order() -> None:
    reader = _FakeReader(
        costs=[_PC(provider="openai", cost_usd=1.23), _PC(provider="anthropic", cost_usd=4.56)]
    )
    handler = CostHandler(reader=reader)

    result = await handler.handle(WindowKey.LAST_HOUR)

    assert result.breakdown == [
        ProviderCostRow(provider="openai", cost_usd=1.23),
        ProviderCostRow(provider="anthropic", cost_usd=4.56),
    ]


async def test_cost_handler_empty_breakdown_is_passed_through() -> None:
    handler = CostHandler(reader=_FakeReader())
    result = await handler.handle(WindowKey.LAST_HOUR)
    assert result.breakdown == []
