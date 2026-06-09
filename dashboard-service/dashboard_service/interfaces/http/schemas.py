"""Wire schemas for the dashboard HTTP API (PRD §7.11)."""

from __future__ import annotations

from pydantic import BaseModel

from dashboard_service.application.use_cases.metric_queries import (
    CostResult,
    ErrorRateResult,
    LatencyResult,
    ProviderCostRow,
    ThroughputResult,
)
from dashboard_service.domain.window import WindowKey


class LatencyView(BaseModel):
    window: WindowKey
    p50: float
    p95: float
    p99: float

    @classmethod
    def from_domain(cls, result: LatencyResult) -> LatencyView:
        return cls(window=result.window, p50=result.p50, p95=result.p95, p99=result.p99)


class ThroughputView(BaseModel):
    window: WindowKey
    request_count: int

    @classmethod
    def from_domain(cls, result: ThroughputResult) -> ThroughputView:
        return cls(window=result.window, request_count=result.request_count)


class ErrorRateView(BaseModel):
    window: WindowKey
    error_rate: float

    @classmethod
    def from_domain(cls, result: ErrorRateResult) -> ErrorRateView:
        return cls(window=result.window, error_rate=result.error_rate)


class CostRowView(BaseModel):
    provider: str
    cost_usd: float

    @classmethod
    def from_domain(cls, row: ProviderCostRow) -> CostRowView:
        return cls(provider=row.provider, cost_usd=row.cost_usd)


class CostView(BaseModel):
    window: WindowKey
    breakdown: list[CostRowView]

    @classmethod
    def from_domain(cls, result: CostResult) -> CostView:
        return cls(
            window=result.window,
            breakdown=[CostRowView.from_domain(r) for r in result.breakdown],
        )
