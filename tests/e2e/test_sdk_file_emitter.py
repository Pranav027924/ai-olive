"""E2E for the SDK FileEmitter (PRD §13 Phase 3.11).

Spins up the real FastAPI app with ``LOG_EMITTER_PATH`` pointing at a
fresh tmp file, runs a single chat turn through the SSE stream, and
verifies that exactly one ``LogEvent`` JSONL line was emitted with all
metadata populated.

Preconditions (auto-skipped if missing):
- ``ANTHROPIC_API_KEY`` is set.
- Postgres + Redis are reachable (compose stack up).
- The ``chat`` schema has been migrated.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from chat_service.config import ChatServiceSettings
from chat_service.infrastructure.persistence.engine import get_sessionmaker
from chat_service.interfaces.http.app import create_app
from contracts.log_event import LogEvent
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

requires_anthropic = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live e2e",
)


@pytest_asyncio.fixture
async def live_client_with_temp_emitter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, Path]]:
    """Build the FastAPI app pointed at an isolated JSONL file."""
    log_path = tmp_path / "inference.jsonl"
    monkeypatch.setenv("LOG_EMITTER_PATH", str(log_path))

    # Clear the lru_caches that hold the previous settings / emitter / SDK
    # client so the new LOG_EMITTER_PATH is picked up.
    from chat_service.interfaces.http import dependencies as deps

    deps._settings.cache_clear()
    deps._sdk_emitter.cache_clear()
    deps._sdk_llm_client.cache_clear()
    deps._redis_client.cache_clear()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, log_path


@requires_anthropic
async def test_chat_turn_emits_a_jsonl_log_event(
    live_client_with_temp_emitter: tuple[AsyncClient, Path],
) -> None:
    client, log_path = live_client_with_temp_emitter
    settings = ChatServiceSettings()
    sm = get_sessionmaker(settings)
    created_sid: UUID | None = None

    try:
        created = await client.post(
            "/sessions",
            json={
                "title": "e2e-sdk",
                "system_prompt": "Answer in one short sentence.",
            },
        )
        assert created.status_code == 201, created.text
        created_sid = UUID(created.json()["id"])

        user_post = await client.post(
            f"/chat/{created_sid}/messages",
            json={"content": "Say the word 'pong' and nothing else."},
        )
        assert user_post.status_code == 201, user_post.text

        # Drain the SSE response — the JSONL line is written when the
        # streaming use case exits its Tracker context (i.e. after the
        # `finished` event is yielded).
        r = await client.get(f"/chat/{created_sid}/stream", timeout=60.0)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "finished" in r.text

        # Verify exactly one JSONL line and parse it back into a LogEvent.
        assert log_path.exists(), f"emitter file missing: {log_path}"
        lines = [ln for ln in log_path.read_text().splitlines() if ln]
        assert len(lines) == 1
        event = LogEvent.model_validate_json(lines[0])

        assert event.session_id == created_sid
        assert event.message_id is not None
        assert event.provider == "anthropic"
        assert event.model == settings.default_model
        assert event.status == "success"
        assert event.latency_ms >= 0
        assert event.ttft_ms is not None
        assert event.ttft_ms >= 0
        assert event.prompt_tokens is not None
        assert event.prompt_tokens > 0
        assert event.completion_tokens is not None
        assert event.completion_tokens > 0
        assert event.input_preview != ""
        assert event.output_preview.strip() != ""
        assert event.sdk_version == "0.1.0"
    finally:
        if created_sid is not None:
            async with sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
