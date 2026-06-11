"""run_worker — long-running CLI entry point (Phase 5.10).

Wires the WorkerLoop to its production dependencies:

    RedisStreamConsumer → ProcessLogEventHandler →
        PostgresLogRepository + RedactionPipeline + CostCalculator

Signals
- SIGTERM and SIGINT are translated to ``WorkerLoop.shutdown()`` so
  the next loop iteration exits cleanly. In-flight ACKs land before
  exit.

Usage::

    uv run python -m worker_service.interfaces.cli.run_worker
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

import aiohttp
from aiochclient import ChClient
from olive_obs import configure_logging
from redis.asyncio import Redis

from worker_service.application.ports.metrics_sink import MetricsSink
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventHandler,
)
from worker_service.application.worker_loop import WorkerLoop
from worker_service.config import WorkerSettings
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.infrastructure.clickhouse.clickhouse_metrics_sink import (
    ClickHouseMetricsSink,
)
from worker_service.infrastructure.persistence.engine import get_sessionmaker
from worker_service.infrastructure.persistence.postgres_log_repo import (
    PostgresLogRepository,
)
from worker_service.infrastructure.redaction.regex_redactor import default_pipeline
from worker_service.infrastructure.streams.redis_dead_letter_sink import (
    RedisDeadLetterSink,
)
from worker_service.infrastructure.streams.redis_stream_consumer import (
    RedisStreamConsumer,
)


def build_loop(settings: WorkerSettings, *, metrics_sink: MetricsSink | None = None) -> WorkerLoop:
    redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    consumer = RedisStreamConsumer(
        redis=redis_client,
        stream=settings.stream_name,
        group=settings.consumer_group,
        consumer_name=settings.consumer_name,
    )
    dead_letter = RedisDeadLetterSink(
        redis=redis_client,
        stream=settings.dlq_stream_name,
        maxlen=settings.dlq_maxlen,
    )
    repo = PostgresLogRepository(get_sessionmaker(settings))
    handler = ProcessLogEventHandler(
        repo=repo,
        pipeline=default_pipeline(),
        cost_calculator=CostCalculator(),
        metrics_sink=metrics_sink,
    )
    return WorkerLoop(
        consumer=consumer,
        handler=handler,
        dead_letter=dead_letter,
        batch_size=settings.batch_size,
        poll_block_ms=settings.poll_block_ms,
    )


async def _periodic_flush(
    sink: ClickHouseMetricsSink, interval: float, stop: asyncio.Event
) -> None:
    """Flush the analytics buffer on a timer so low-traffic rows still
    land in ClickHouse without waiting for the buffer to fill."""
    while not stop.is_set():
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
        await sink.flush()


async def _amain() -> None:
    configure_logging(service="worker-service")
    settings = WorkerSettings()

    session = aiohttp.ClientSession()
    ch_client = ChClient(
        session,
        url=settings.clickhouse_url,
        user=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_db,
    )
    sink = ClickHouseMetricsSink(
        client=ch_client,
        buffer_size=settings.clickhouse_buffer_size,
        flush_interval_seconds=settings.clickhouse_flush_interval_seconds,
    )

    loop = build_loop(settings, metrics_sink=sink)

    asyncio_loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio_loop.add_signal_handler(sig, loop.shutdown)

    flusher = asyncio.create_task(
        _periodic_flush(sink, settings.clickhouse_flush_interval_seconds, loop.shutdown_event)
    )
    try:
        await loop.run_forever()
    finally:
        flusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await flusher
        await sink.close()
        await session.close()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
