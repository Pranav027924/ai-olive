"""ClickHouseMetricsSink — buffered writer for inference_metrics (PRD §7.5).

Buffers :class:`ProcessedLog` rows in memory and flushes them as a
single ClickHouse batch INSERT when either:

- ``buffer_size`` rows have accumulated, or
- ``flush_interval_seconds`` have elapsed since the previous flush.

The HTTP call uses aiochclient. A flush failure does **not** roll
back the corresponding Postgres write — analytics is a best-effort
mirror; we log the exception and keep the rows in-buffer so the
next flush retries.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from worker_service.application.ports.metrics_sink import MetricsSink
from worker_service.domain.entities.processed_log import ProcessedLog

logger = logging.getLogger(__name__)

INSERT_SQL = (
    "INSERT INTO inference_metrics "
    "(event_id, session_id, provider, model, status, "
    "started_at, finished_at, latency_ms, ttft_ms, "
    "prompt_tokens, completion_tokens, cost_usd) VALUES"
)


class ClickHouseMetricsSink(MetricsSink):
    def __init__(
        self,
        *,
        client: Any,
        buffer_size: int = 100,
        flush_interval_seconds: float = 5.0,
    ) -> None:
        if buffer_size < 1:
            raise ValueError("buffer_size must be >= 1")
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be > 0")
        self._client = client
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval_seconds
        self._buffer: list[ProcessedLog] = []
        self._lock = asyncio.Lock()
        self._last_flush = time.monotonic()

    async def record(self, processed: ProcessedLog) -> None:
        async with self._lock:
            self._buffer.append(processed)
            should_flush = (
                len(self._buffer) >= self._buffer_size
                or (time.monotonic() - self._last_flush) >= self._flush_interval
            )
        if should_flush:
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()

        rows = [_to_row(p) for p in batch]
        try:
            await self._client.execute(INSERT_SQL, *rows)
        except Exception:
            logger.exception("clickhouse flush failed; %d rows re-queued", len(batch))
            async with self._lock:
                # Put the unflushed batch back at the head so the next
                # attempt drains it first.
                self._buffer[:0] = batch
            return
        self._last_flush = time.monotonic()

    async def close(self) -> None:
        await self.flush()
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()


def _to_row(p: ProcessedLog) -> tuple[Any, ...]:
    return (
        p.id,
        p.session_id,
        p.provider,
        p.model,
        p.status,
        p.started_at,
        p.finished_at,
        p.latency_ms,
        p.ttft_ms,
        p.prompt_tokens or 0,
        p.completion_tokens or 0,
        float(p.cost_usd) if p.cost_usd is not None else 0.0,
    )
