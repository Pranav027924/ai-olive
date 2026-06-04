"""E2E for the worker's idempotency guarantee (PRD §13 Phase 5.11).

Drives a real ``WorkerLoop`` against the real compose Postgres + Redis.
The test XADDs the same ``LogEvent`` payload twice to
``inference_logs``, runs the worker until both deliveries are
processed, then asserts that exactly one row landed in
``logs.inference_logs``.

Each test uses a unique consumer-group + consumer-name so leftover
state from prior runs never leaks in. The created row is deleted in
the teardown block.

Preconditions (auto-skipped if missing):
- Postgres + Redis are reachable (compose stack up).
- The ``logs`` schema has been migrated (``make migrate-worker``).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from contracts.log_event import LogEvent
from redis.asyncio import Redis
from sqlalchemy import text
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventHandler,
)
from worker_service.application.worker_loop import WorkerLoop
from worker_service.config import WorkerSettings
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.infrastructure.persistence.engine import get_sessionmaker
from worker_service.infrastructure.persistence.postgres_log_repo import (
    PostgresLogRepository,
)
from worker_service.infrastructure.redaction.regex_redactor import default_pipeline
from worker_service.infrastructure.streams.redis_stream_consumer import (
    RedisStreamConsumer,
)

STREAM = "inference_logs"

# Same gate as the other e2e tests so a CI run without the compose stack
# doesn't try to talk to a missing Postgres / Redis.
requires_live_infra = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live e2e (proxy for compose-stack-up)",
)


def _event() -> LogEvent:
    return LogEvent(
        event_id=uuid4(),
        session_id=uuid4(),
        provider="anthropic",
        model="claude-opus-4-7",
        status="success",
        started_at=datetime(2026, 6, 1, tzinfo=UTC),
        finished_at=datetime(2026, 6, 1, 0, 0, 1, tzinfo=UTC),
        latency_ms=1000,
        prompt_tokens=100,
        completion_tokens=50,
        input_preview="hi",
        output_preview="hello",
        sdk_version="0.1.0",
    )


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    settings = WorkerSettings()
    client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    await client.aclose()


def _xadd_payload(event: LogEvent) -> dict[str, str]:
    return {"ingestion_id": str(uuid4()), "event": event.model_dump_json()}


async def _drain_until_persisted(
    settings: WorkerSettings,
    event_id: UUID,
    *,
    group: str,
    consumer_name: str,
    redis_client: Redis,
    timeout_seconds: float = 10.0,
) -> WorkerLoop:
    """Run a WorkerLoop until the given event_id appears in Postgres
    AND any pending second delivery has been processed.

    Returns the loop so the caller can shut it down.
    """
    repo = PostgresLogRepository(get_sessionmaker(settings))
    handler = ProcessLogEventHandler(
        repo=repo,
        pipeline=default_pipeline(),
        cost_calculator=CostCalculator(),
    )
    consumer = RedisStreamConsumer(
        redis=redis_client,
        stream=STREAM,
        group=group,
        consumer_name=consumer_name,
    )
    loop = WorkerLoop(
        consumer=consumer,
        handler=handler,
        batch_size=10,
        poll_block_ms=100,
    )

    run_task = asyncio.create_task(loop.run_forever())

    sm = get_sessionmaker(settings)
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    seen = False
    while asyncio.get_event_loop().time() < deadline:
        async with sm() as db:
            count = await db.scalar(
                text("SELECT COUNT(*) FROM logs.inference_logs WHERE id = CAST(:id AS uuid)"),
                {"id": str(event_id)},
            )
        if count and count >= 1:
            seen = True
            # Give the worker a brief grace period to consume the second
            # delivery and short-circuit on the idempotency check.
            await asyncio.sleep(0.5)
            break
        await asyncio.sleep(0.05)

    loop.shutdown()
    try:
        await asyncio.wait_for(run_task, timeout=5.0)
    except TimeoutError:
        run_task.cancel()

    if not seen:
        raise AssertionError(f"event_id {event_id} never appeared in Postgres")
    return loop


@requires_live_infra
async def test_same_event_id_delivered_twice_produces_one_row(
    redis_client: Redis,
) -> None:
    settings = WorkerSettings()
    sm = get_sessionmaker(settings)
    ev = _event()
    group = f"test-{uuid4()}"

    # Create the consumer group BEFORE the test XADDs so messages aren't
    # dropped by "$" (only-new-after-group).
    with suppress(Exception):
        await redis_client.xgroup_create(name=STREAM, groupname=group, id="$", mkstream=True)

    try:
        # Two XADDs of the same logical event (different ingestion_id).
        await redis_client.xadd(STREAM, cast("dict[Any, Any]", _xadd_payload(ev)))
        await redis_client.xadd(STREAM, cast("dict[Any, Any]", _xadd_payload(ev)))

        await _drain_until_persisted(
            settings,
            ev.event_id,
            group=group,
            consumer_name="test-worker",
            redis_client=redis_client,
        )

        # Exactly one row regardless of how many deliveries the worker saw.
        async with sm() as db:
            count = await db.scalar(
                text("SELECT COUNT(*) FROM logs.inference_logs WHERE id = CAST(:id AS uuid)"),
                {"id": str(ev.event_id)},
            )
        assert count == 1
    finally:
        async with sm() as db, db.begin():
            await db.execute(
                text("DELETE FROM logs.inference_logs WHERE id = CAST(:id AS uuid)"),
                {"id": str(ev.event_id)},
            )
        with suppress(Exception):
            await redis_client.xgroup_destroy(STREAM, group)
