"""E2E for the chat-service → SDK HttpEmitter → ingestion → Redis Streams
pipeline (PRD §13 Phase 4.11).

Wires the real chat-service FastAPI app to an in-process ingestion
FastAPI app via ``httpx.ASGITransport``, then drives one chat turn
end-to-end. After the SSE stream completes (which triggers the SDK
Tracker's exit hook → HTTP emit), the test asserts that a new
``LogEvent`` row appeared on the real compose-Redis
``inference_logs`` stream and that it round-trips through
:meth:`LogEvent.model_validate_json`.

Preconditions (auto-skipped if missing):
- ``ANTHROPIC_API_KEY`` is set.
- Postgres + Redis are reachable (compose stack up).
- The ``chat`` schema has been migrated.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from chat_service.config import ChatServiceSettings
from chat_service.infrastructure.persistence.engine import get_sessionmaker
from chat_service.interfaces.http.app import create_app as create_chat_app
from contracts.log_event import LogEvent
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

requires_anthropic = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live e2e",
)

STREAM_NAME = "inference_logs"


class _AlwaysOkAuth(AuthProvider):
    def is_valid(self, api_key: str) -> bool:
        return True


@pytest_asyncio.fixture
async def live_pipeline(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, Redis]]:
    log_path = tmp_path / "inference.jsonl"

    # Build the ingestion app first; auth is replaced with always-ok, real
    # compose Redis is used for the stream.
    ingestion_app = create_ingestion_app()
    ingestion_app.dependency_overrides[get_auth_provider] = lambda: _AlwaysOkAuth()

    # An httpx.AsyncClient pointed at the ingestion ASGI app so the SDK
    # HttpEmitter can speak to it without touching the network.
    ingestion_transport = httpx.ASGITransport(app=ingestion_app)
    ingestion_client = httpx.AsyncClient(
        transport=ingestion_transport, base_url="http://ingestion-test"
    )

    # Build the chat app and override its emitter to use the SDK's
    # CompositeEmitter([HttpEmitter(custom client), FileEmitter]) so we
    # exercise the real production wiring end-to-end.
    chat_app = create_chat_app()

    http_emitter = HttpEmitter(
        endpoint="http://ingestion-test/v1/logs",
        api_key="ignored-by-always-ok-auth",
        max_batch=1,
        flush_interval_seconds=0.05,
        client=ingestion_client,
    )
    composite: EmitterPort = CompositeEmitter(emitters=[http_emitter, FileEmitter(path=log_path)])

    from chat_service.interfaces.http import dependencies as deps

    # Clear caches so the new emitter wiring + Redis client are picked up.
    deps._settings.cache_clear()
    deps._sdk_emitter.cache_clear()
    deps._sdk_llm_client.cache_clear()
    deps._redis_client.cache_clear()
    chat_app.dependency_overrides[deps.get_settings] = ChatServiceSettings
    chat_app.dependency_overrides[deps._sdk_emitter] = lambda: composite

    settings = ChatServiceSettings()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

    async with AsyncClient(transport=ASGITransport(app=chat_app), base_url="http://chat-test") as c:
        yield c, redis_client

    await http_emitter.aclose()
    await ingestion_client.aclose()
    await redis_client.aclose()


@requires_anthropic
async def test_chat_turn_lands_on_redis_inference_logs_stream(
    live_pipeline: tuple[AsyncClient, Redis],
) -> None:
    client, redis_client = live_pipeline
    settings = ChatServiceSettings()
    sm = get_sessionmaker(settings)

    xlen_before = await redis_client.xlen(STREAM_NAME)

    created_sid: UUID | None = None
    try:
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

        # Let the HttpEmitter background worker drain — flush_interval is 50ms.
        for _ in range(40):
            await asyncio.sleep(0.05)
            xlen_after = await redis_client.xlen(STREAM_NAME)
            if xlen_after >= xlen_before + 1:
                break
        else:
            pytest.fail(f"expected XLEN delta >= 1; before={xlen_before} after={xlen_after}")

        assert xlen_after == xlen_before + 1

        # Read the newest entry and validate the LogEvent.
        entries = await redis_client.xrevrange(STREAM_NAME, count=1)
        assert entries
        _stream_id, payload = entries[0]
        assert payload is not None
        assert payload["ingestion_id"]
        event = LogEvent.model_validate_json(payload["event"])
        assert event.session_id == created_sid
        assert event.provider == "anthropic"
        assert event.status == "success"
    finally:
        if created_sid is not None:
            async with sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
