"""MetricsReader — outbound port for dashboard analytics (PRD §7.10)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class LatencyPercentiles(Protocol):
    p50: float
    p95: float
    p99: float


class ProviderCost(Protocol):
    provider: str
    cost_usd: float


class MetricsReader(Protocol):
    async def latency_percentiles(self, *, since: datetime, until: datetime) -> LatencyPercentiles:
        """Return p50/p95/p99 latency (ms) over ``[since, until)``."""

    async def throughput(self, *, since: datetime, until: datetime) -> int:
        """Return total request count over ``[since, until)``."""

    async def error_rate(self, *, since: datetime, until: datetime) -> float:
        """Return error_count / total_count over ``[since, until)``, 0.0 if empty."""

    async def cost_by_provider(self, *, since: datetime, until: datetime) -> list[ProviderCost]:
        """Return total USD spend per provider over ``[since, until)``."""
