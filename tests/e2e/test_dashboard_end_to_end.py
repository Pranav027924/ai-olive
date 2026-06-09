"""End-to-end dashboard test (Phase 7.12).

Writes a handful of synthetic rows directly into ClickHouse, then
hits each /metrics endpoint and asserts shapes + sanity values.

Preconditions (skipped automatically if not met):
- ClickHouse is reachable at ``CLICKHOUSE_URL`` (default
  http://127.0.0.1:8123, brought up via ``make up-analytics``).
- The inference_metrics table has been migrated
  (``make migrate-clickhouse``).
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import aiohttp
import pytest
import pytest_asyncio
from aiochclient import ChClient
from dashboard_service.config import DashboardServiceSettings
from dashboard_service.interfaces.http.app import create_app
from httpx import ASGITransport, AsyncClient


def _clickhouse_reachable() -> bool:
    settings = DashboardServiceSettings()
    host = settings.clickhouse_url.replace("http://", "").replace("https://", "")
    host, _, port = host.partition(":")
    try:
        with socket.create_connection((host, int(port or "8123")), timeout=0.25):
            return True
    except OSError:
        return False


requires_clickhouse = pytest.mark.skipif(
    not _clickhouse_reachable(),
    reason="ClickHouse not reachable; run `make up-analytics && make migrate-clickhouse`",
)


@pytest.fixture
def settings() -> DashboardServiceSettings:
    return DashboardServiceSettings()


@pytest_asyncio.fixture
async def ch_client(settings: DashboardServiceSettings) -> AsyncIterator[ChClient]:
    async with aiohttp.ClientSession() as session:
        client = ChClient(
            session,
            url=settings.clickhouse_url,
            user=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_db,
        )
        yield client


@pytest_asyncio.fixture
async def dashboard_client(settings: DashboardServiceSettings) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _seed(ch_client: ChClient, *, n: int = 6, error_count: int = 2) -> str:
    """Insert N inference_metrics rows tagged with a unique provider so
    we can scope assertions to just this test's data."""
    label = f"e2e-{uuid4().hex[:8]}"
    now = datetime.now(tz=UTC)
    rows = []
    for i in range(n):
        rows.append(
            (
                uuid4(),
                uuid4(),
                label,
                "model-x",
                "error" if i < error_count else "success",
                now - timedelta(minutes=i + 1),
                now - timedelta(minutes=i),
                100 + i * 10,
                None,
                10,
                20,
                0.5,
            )
        )
    await ch_client.execute(
        "INSERT INTO inference_metrics "
        "(event_id, session_id, provider, model, status, started_at, finished_at, "
        "latency_ms, ttft_ms, prompt_tokens, completion_tokens, cost_usd) VALUES",
        *rows,
    )
    return label


@requires_clickhouse
async def test_dashboard_endpoints_return_correct_shapes(
    dashboard_client: AsyncClient, ch_client: ChClient
) -> None:
    await _seed(ch_client, n=6, error_count=2)

    for path, required_keys in [
        ("/metrics/latency?window=1h", {"window", "p50", "p95", "p99"}),
        ("/metrics/throughput?window=1h", {"window", "request_count"}),
        ("/metrics/error-rate?window=1h", {"window", "error_rate"}),
        ("/metrics/cost?window=1h", {"window", "breakdown"}),
    ]:
        r = await dashboard_client.get(path)
        assert r.status_code == 200, f"{path} -> {r.text}"
        body = r.json()
        assert required_keys.issubset(body.keys())


@requires_clickhouse
async def test_throughput_grows_after_inserting_rows(
    dashboard_client: AsyncClient, ch_client: ChClient
) -> None:
    before = (await dashboard_client.get("/metrics/throughput?window=1h")).json()["request_count"]
    await _seed(ch_client, n=3, error_count=0)
    after = (await dashboard_client.get("/metrics/throughput?window=1h")).json()["request_count"]
    assert after - before >= 3
