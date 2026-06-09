"""FastAPI dependency providers for the dashboard-service."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import aiohttp
from aiochclient import ChClient
from fastapi import Depends

from dashboard_service.application.ports.metrics_reader import MetricsReader
from dashboard_service.application.use_cases.metric_queries import (
    CostHandler,
    ErrorRateHandler,
    LatencyPercentilesHandler,
    ThroughputHandler,
)
from dashboard_service.config import DashboardServiceSettings
from dashboard_service.infrastructure.clickhouse.clickhouse_metrics_reader import (
    ClickHouseMetricsReader,
)


@lru_cache(maxsize=1)
def _settings() -> DashboardServiceSettings:
    return DashboardServiceSettings()


def get_settings() -> DashboardServiceSettings:
    return _settings()


SettingsDep = Annotated[DashboardServiceSettings, Depends(get_settings)]


@lru_cache(maxsize=1)
def _metrics_reader() -> MetricsReader:
    settings = _settings()
    session = aiohttp.ClientSession()
    client = ChClient(
        session,
        url=settings.clickhouse_url,
        user=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
    )
    return ClickHouseMetricsReader(client=client, table=settings.clickhouse_table)


def get_metrics_reader(settings: SettingsDep) -> MetricsReader:
    return _metrics_reader()


ReaderDep = Annotated[MetricsReader, Depends(get_metrics_reader)]


@lru_cache(maxsize=1)
def _health_client() -> ChClient:
    settings = _settings()
    session = aiohttp.ClientSession()
    return ChClient(
        session,
        url=settings.clickhouse_url,
        user=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
    )


async def clickhouse_health_check() -> None:
    """Readiness probe dependency: raises if ClickHouse is unreachable (PRD §9.3)."""
    alive = await _health_client().is_alive()
    if not alive:
        raise RuntimeError("clickhouse is_alive() returned False")


def get_latency_handler(reader: ReaderDep) -> LatencyPercentilesHandler:
    return LatencyPercentilesHandler(reader=reader)


def get_throughput_handler(reader: ReaderDep) -> ThroughputHandler:
    return ThroughputHandler(reader=reader)


def get_error_rate_handler(reader: ReaderDep) -> ErrorRateHandler:
    return ErrorRateHandler(reader=reader)


def get_cost_handler(reader: ReaderDep) -> CostHandler:
    return CostHandler(reader=reader)


LatencyDep = Annotated[LatencyPercentilesHandler, Depends(get_latency_handler)]
ThroughputDep = Annotated[ThroughputHandler, Depends(get_throughput_handler)]
ErrorRateDep = Annotated[ErrorRateHandler, Depends(get_error_rate_handler)]
CostDep = Annotated[CostHandler, Depends(get_cost_handler)]
