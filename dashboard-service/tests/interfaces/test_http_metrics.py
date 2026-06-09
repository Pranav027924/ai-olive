"""HTTP tests for the dashboard /metrics endpoints (Phase 7.11)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

import pytest
import pytest_asyncio
from dashboard_service.application.ports.metrics_reader import (
    LatencyPercentiles,
    MetricsReader,
    ProviderCost,
)
from dashboard_service.interfaces.http.app import create_app
from dashboard_service.interfaces.http.dependencies import get_metrics_reader
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@dataclass
class _Lat:
    p50: float
    p95: float
    p99: float


@dataclass
class _PC:
    provider: str
    cost_usd: float


class _FakeReader(MetricsReader):
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

    async def latency_percentiles(self, *, since: datetime, until: datetime) -> LatencyPercentiles:
        return self._latency

    async def throughput(self, *, since: datetime, until: datetime) -> int:
        return self._throughput

    async def error_rate(self, *, since: datetime, until: datetime) -> float:
        return self._error_rate

    async def cost_by_provider(self, *, since: datetime, until: datetime) -> list[ProviderCost]:
        return list(self._costs)


@pytest.fixture
def fake_reader() -> _FakeReader:
    return _FakeReader(
        latency=_Lat(p50=120, p95=300, p99=900),
        throughput_value=42,
        error_rate_value=0.125,
        costs=[_PC(provider="openai", cost_usd=1.23)],
    )


@pytest.fixture
def app(fake_reader: _FakeReader) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_metrics_reader] = lambda: fake_reader
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_latency_default_window_is_one_hour(client: AsyncClient) -> None:
    r = await client.get("/metrics/latency")
    assert r.status_code == 200
    body = r.json()
    assert body == {"window": "1h", "p50": 120.0, "p95": 300.0, "p99": 900.0}


async def test_latency_window_query_param(client: AsyncClient) -> None:
    r = await client.get("/metrics/latency?window=24h")
    assert r.status_code == 200
    assert r.json()["window"] == "24h"


async def test_throughput_returns_request_count(client: AsyncClient) -> None:
    r = await client.get("/metrics/throughput?window=24h")
    assert r.status_code == 200
    assert r.json() == {"window": "24h", "request_count": 42}


async def test_error_rate_returns_ratio(client: AsyncClient) -> None:
    r = await client.get("/metrics/error-rate?window=7d")
    assert r.status_code == 200
    assert r.json() == {"window": "7d", "error_rate": 0.125}


async def test_cost_returns_breakdown(client: AsyncClient) -> None:
    r = await client.get("/metrics/cost?window=1h")
    assert r.status_code == 200
    assert r.json() == {
        "window": "1h",
        "breakdown": [{"provider": "openai", "cost_usd": 1.23}],
    }


async def test_invalid_window_returns_422(client: AsyncClient) -> None:
    r = await client.get("/metrics/latency?window=99h")
    assert r.status_code == 422
