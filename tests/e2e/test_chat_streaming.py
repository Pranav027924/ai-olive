"""E2E for SSE streaming + cancellation (PRD §13 Phase 2.8).

Two flows, both against the real Anthropic API, the real compose
Postgres, and the real compose Redis:

  1. Open ``GET /chat/{id}/stream`` for a session that has a pending
     user message. Verify the SSE response framing:
       event: started   first
       event: chunk     >= 1 occurrences carrying assistant text
       event: finished  state=completed, joined content non-empty
     Then verify the assistant message was persisted with
     status='complete'.

  2. POST ``/chat/{id}/cancel`` *before* opening the stream. The
     handler still emits one StreamStarted event, then immediately
     sees the cancel flag and yields StreamFinished with
     state=cancelled and empty content. The persisted assistant
     message has status='cancelled'.

Preconditions (auto-skipped if missing):
- ``ANTHROPIC_API_KEY`` is set.
- Postgres is reachable and the chat schema has been migrated.
- Redis is reachable on REDIS_HOST:REDIS_PORT.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from chat_service.config import ChatServiceSettings
from chat_service.infrastructure.persistence.engine import get_sessionmaker
from chat_service.interfaces.http.app import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

requires_anthropic = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live e2e",
)


@pytest.fixture
def settings() -> ChatServiceSettings:
    return ChatServiceSettings()


@pytest_asyncio.fixture
async def live_client(settings: ChatServiceSettings) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _parse_sse(body: str) -> list[tuple[str, str]]:
    """Return a flat list of (event_name, data_str) pairs from raw SSE text."""
    events: list[tuple[str, str]] = []
    current_event: str | None = None
    for raw_line in body.splitlines():
        if raw_line.startswith("event:"):
            current_event = raw_line[len("event:") :].strip()
        elif raw_line.startswith("data:"):
            data = raw_line[len("data:") :].strip()
            events.append((current_event or "message", data))
            current_event = None
    return events


async def _delete_session(settings: ChatServiceSettings, sid: UUID) -> None:
    sm = get_sessionmaker(settings)
    async with sm() as db, db.begin():
        await db.execute(
            text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
            {"sid": str(sid)},
        )


@requires_anthropic
async def test_stream_yields_assistant_text_token_by_token(
    live_client: AsyncClient, settings: ChatServiceSettings
) -> None:
    created_sid: UUID | None = None
    try:
        created = await live_client.post(
            "/sessions",
            json={
                "title": "e2e-stream",
                "system_prompt": "Answer in 1-2 short sentences.",
            },
        )
        assert created.status_code == 201, created.text
        created_sid = UUID(created.json()["id"])

        user_msg = await live_client.post(
            f"/chat/{created_sid}/messages",
            json={"content": "Count from 1 to 5, separated by commas."},
        )
        assert user_msg.status_code == 201, user_msg.text

        r = await live_client.get(f"/chat/{created_sid}/stream", timeout=60.0)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(r.text)
        names = [n for n, _ in events]
        assert names[0] == "started"
        assert names[-1] == "finished"
        assert "chunk" in names, "expected at least one streaming chunk"

        finished = json.loads(events[-1][1])
        assert finished["state"] == "completed"
        assert finished["content"].strip() != ""
        # The joined chunks should equal the final content.
        joined = "".join(json.loads(d)["text"] for n, d in events if n == "chunk")
        assert joined == finished["content"]

        # Persistence check: assistant message saved with status=complete.
        sm = get_sessionmaker(settings)
        async with sm() as db:
            row = await db.execute(
                text(
                    "SELECT status FROM chat.messages "
                    "WHERE session_id = CAST(:sid AS uuid) AND role = 'assistant'"
                ),
                {"sid": str(created_sid)},
            )
            statuses = [r[0] for r in row.all()]
            assert statuses == ["complete"]
    finally:
        if created_sid is not None:
            await _delete_session(settings, created_sid)


@requires_anthropic
async def test_cancel_before_stream_finishes_cancelled(
    live_client: AsyncClient, settings: ChatServiceSettings
) -> None:
    created_sid: UUID | None = None
    try:
        created = await live_client.post("/sessions", json={"title": "e2e-cancel"})
        assert created.status_code == 201, created.text
        created_sid = UUID(created.json()["id"])

        await live_client.post(
            f"/chat/{created_sid}/messages",
            json={"content": "say something"},
        )

        # Flip the cancel flag via the public endpoint *before* we open the stream.
        cancel = await live_client.post(f"/chat/{created_sid}/cancel")
        assert cancel.status_code == 204, cancel.text

        r = await live_client.get(f"/chat/{created_sid}/stream", timeout=60.0)
        assert r.status_code == 200, r.text

        events = _parse_sse(r.text)
        names = [n for n, _ in events]
        assert names[0] == "started"
        assert names[-1] == "finished"
        finished = json.loads(events[-1][1])
        assert finished["state"] == "cancelled"
        assert finished["content"] == ""

        sm = get_sessionmaker(settings)
        async with sm() as db:
            row = await db.execute(
                text(
                    "SELECT status, content FROM chat.messages "
                    "WHERE session_id = CAST(:sid AS uuid) AND role = 'assistant'"
                ),
                {"sid": str(created_sid)},
            )
            rows = row.all()
            assert len(rows) == 1
            assert rows[0][0] == "cancelled"
            assert rows[0][1] == ""
    finally:
        if created_sid is not None:
            await _delete_session(settings, created_sid)
