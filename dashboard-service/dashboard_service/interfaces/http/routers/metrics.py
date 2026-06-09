"""Metric endpoints (PRD §7.11)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from dashboard_service.domain.window import WindowKey
from dashboard_service.interfaces.http.dependencies import (
    CostDep,
    ErrorRateDep,
    LatencyDep,
    ThroughputDep,
)
from dashboard_service.interfaces.http.schemas import (
    CostView,
    ErrorRateView,
    LatencyView,
    ThroughputView,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])

WindowQuery = Annotated[WindowKey, Query(alias="window")]


@router.get("/latency", response_model=LatencyView)
async def latency(handler: LatencyDep, window: WindowQuery = WindowKey.LAST_HOUR) -> LatencyView:
    return LatencyView.from_domain(await handler.handle(window))


@router.get("/throughput", response_model=ThroughputView)
async def throughput(
    handler: ThroughputDep, window: WindowQuery = WindowKey.LAST_HOUR
) -> ThroughputView:
    return ThroughputView.from_domain(await handler.handle(window))


@router.get("/error-rate", response_model=ErrorRateView)
async def error_rate(
    handler: ErrorRateDep, window: WindowQuery = WindowKey.LAST_HOUR
) -> ErrorRateView:
    return ErrorRateView.from_domain(await handler.handle(window))


@router.get("/cost", response_model=CostView)
async def cost(handler: CostDep, window: WindowQuery = WindowKey.LAST_HOUR) -> CostView:
    return CostView.from_domain(await handler.handle(window))
