"""MetricsSink — outbound port for analytics writes (PRD §7.5).

The worker mirrors every successful Postgres insert into the
analytics backend so the dashboard service can run aggregate
queries without going through the OLTP store. The adapter buffers
internally and flushes either when ``buffer_size`` is reached or
``flush_interval_seconds`` has elapsed since the last flush — the
caller doesn't see the batching.
"""

from __future__ import annotations

from typing import Protocol

from worker_service.domain.entities.processed_log import ProcessedLog


class MetricsSink(Protocol):
    async def record(self, processed: ProcessedLog) -> None:
        """Enqueue ``processed`` for async batch insert."""

    async def flush(self) -> None:
        """Force any buffered rows to be written immediately."""

    async def close(self) -> None:
        """Flush + release the underlying transport."""
