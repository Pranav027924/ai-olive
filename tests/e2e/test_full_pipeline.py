"""E2E for the full logging pipeline (PRD §13 Phase 5.12).

Wires every service in process and drives a real chat turn against
the real Anthropic API:

    React UI shape  → chat-service (real FastAPI app)
        → olive-sdk HttpEmitter (via httpx.ASGITransport)
            → ingestion-service (real FastAPI app)
                → real compose Redis (XADD inference_logs)
                    → worker-service (real WorkerLoop)
                        → real compose Postgres
                            → logs.inference_logs row

The assertion is "exactly one row appears in ``logs.inference_logs``
with this turn's session_id" — proving the entire chain works.

Preconditions (auto-skipped if missing):
- ``ANTHROPIC_API_KEY`` is set (real LLM call).
- Postgres + Redis are reachable (compose stack up).
- ``logs`` and ``chat`` schemas migrated (``make migrate-all``).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from chat_service.config import ChatServiceSettings
from chat_service.infrastructure.persistence.engine import (
    get_sessionmaker as get_chat_sessionmaker,
)
from chat_service.interfaces.http.app import create_app as create_chat_app
from httpx import ASGITransport, AsyncClient
from ingestion_service.application.ports.auth_provider import AuthProvider
from ingestion_service.interfaces.http.app import create_app as create_ingestion_app
from ingestion_service.interfaces.http.dependencies import get_auth_provider
from olive_sdk.application.emitter_port import EmitterPort
from olive_sdk.infrastructure.emitters.composite_emitter import CompositeEmitter
from olive_sdk.infrastructure.emitters.file_emitter import FileEmitter
from olive_sdk.infrastructure.emitters.http_emitter import HttpEmitter
from redis.asyncio import Redis
from sqlalchemy import text
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventHandler,
)
from worker_service.application.worker_loop import WorkerLoop
from worker_service.config import WorkerSettings
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.infrastructure.persistence.engine import (
    get_sessionmaker as get_worker_sessionmaker,
)
from worker_service.infrastructure.persistence.postgres_log_repo import (
    PostgresLogRepository,
)
from worker_service.infrastructure.redaction.regex_redactor import default_pipeline
from worker_service.infrastructure.streams.redis_stream_consumer import (
    RedisStreamConsumer,
)

STREAM = "inference_logs"

requires_anthropic = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live e2e",
)


class _AlwaysOkAuth(AuthProvider):
    def is_valid(self, api_key: str) -> bool:
        return True


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    settings = WorkerSettings()
    client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    await client.aclose()


async def _drain_until_session_persisted(
    worker_settings: WorkerSettings,
    session_id: UUID,
    *,
    group: str,
    consumer_name: str,
    redis_client: Redis,
    timeout_seconds: float = 30.0,
) -> None:
    """Run a WorkerLoop until at least one row with this session_id lands
    in Postgres."""
    repo = PostgresLogRepository(get_worker_sessionmaker(worker_settings))
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
    loop = WorkerLoop(consumer=consumer, handler=handler, batch_size=10, poll_block_ms=100)

    run_task = asyncio.create_task(loop.run_forever())
    sm = get_worker_sessionmaker(worker_settings)
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    found = False
    while asyncio.get_event_loop().time() < deadline:
        async with sm() as db:
            count = await db.scalar(
                text(
                    "SELECT COUNT(*) FROM logs.inference_logs WHERE session_id = CAST(:sid AS uuid)"
                ),
                {"sid": str(session_id)},
            )
        if count and count >= 1:
            found = True
            break
        await asyncio.sleep(0.1)

    loop.shutdown()
    try:
        await asyncio.wait_for(run_task, timeout=5.0)
    except TimeoutError:
        run_task.cancel()

    if not found:
        raise AssertionError(f"no logs.inference_logs row appeared for session_id={session_id}")


@requires_anthropic
async def test_chat_turn_lands_in_postgres_via_full_pipeline(
    redis_client: Redis,
    tmp_path: Path,
) -> None:
    chat_settings = ChatServiceSettings()
    worker_settings = WorkerSettings()
    chat_sm = get_chat_sessionmaker(chat_settings)
    worker_sm = get_worker_sessionmaker(worker_settings)

    # Build the ingestion ASGI app and override its auth.
    ingestion_app = create_ingestion_app()
    ingestion_app.dependency_overrides[get_auth_provider] = lambda: _AlwaysOkAuth()
    ingestion_transport = httpx.ASGITransport(app=ingestion_app)
    ingestion_client = httpx.AsyncClient(
        transport=ingestion_transport, base_url="http://ingestion-test"
    )

    # Build the chat-service app and override its emitter to ship to the
    # in-process ingestion app while still tee'ing to a tmp file.
    chat_app = create_chat_app()
    http_emitter = HttpEmitter(
        endpoint="http://ingestion-test/v1/logs",
        api_key="any-key",
        max_batch=1,
        flush_interval_seconds=0.05,
        client=ingestion_client,
    )
    composite: EmitterPort = CompositeEmitter(
        emitters=[http_emitter, FileEmitter(path=tmp_path / "inference.jsonl")]
    )

    from chat_service.interfaces.http import dependencies as deps

    deps._settings.cache_clear()
    deps._sdk_emitter.cache_clear()
    deps._sdk_llm_client.cache_clear()
    deps._redis_client.cache_clear()
    chat_app.dependency_overrides[deps._sdk_emitter] = lambda: composite

    # Per-test consumer group on the real Redis stream.
    group = f"e2e-pipeline-{uuid4()}"
    with suppress(Exception):
        await redis_client.xgroup_create(name=STREAM, groupname=group, id="$", mkstream=True)

    created_sid: UUID | None = None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=chat_app), base_url="http://chat-test"
        ) as client:
            created = await client.post(
                "/sessions",
                json={"system_prompt": "Answer in one short sentence."},
            )
            assert created.status_code == 201, created.text
            created_sid = UUID(created.json()["id"])

            await client.post(
                f"/chat/{created_sid}/messages",
                json={"content": "Say 'pong' and nothing else."},
            )
            r = await client.get(f"/chat/{created_sid}/stream", timeout=60.0)
            assert r.status_code == 200, r.text
            assert "finished" in r.text

        # Let HttpEmitter drain (50ms flush) so the ingestion XADD lands.
        await asyncio.sleep(0.2)

        await _drain_until_session_persisted(
            worker_settings,
            created_sid,
            group=group,
            consumer_name="e2e-worker",
            redis_client=redis_client,
        )

        # Verify exactly one inference_logs row carrying this session id.
        async with worker_sm() as db:
            row = await db.execute(
                text(
                    "SELECT provider, model, status, session_id "
                    "FROM logs.inference_logs WHERE session_id = CAST(:sid AS uuid)"
                ),
                {"sid": str(created_sid)},
            )
            rows = row.mappings().all()
        assert len(rows) == 1
        assert rows[0]["provider"] == "anthropic"
        assert rows[0]["status"] == "success"
    finally:
        if created_sid is not None:
            async with chat_sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
            async with worker_sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM logs.inference_logs WHERE session_id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
        await http_emitter.aclose()
        await ingestion_client.aclose()
        with suppress(Exception):
            await redis_client.xgroup_destroy(STREAM, group)
