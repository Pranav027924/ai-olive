"""End-to-end test for the chat-service happy path (Phase 1.11).

Exercises the real FastAPI app against the real Postgres compose
service and the real Anthropic API:

  POST /sessions              create a session
  POST /chat/{id}/messages    send a user message, get an assistant reply
  Postgres                    verify session + 2 messages persisted

Preconditions (skipped automatically if not met):
- ``ANTHROPIC_API_KEY`` is set in the environment.
- Postgres is reachable on ``POSTGRES_HOST:POSTGRES_PORT``.
- The ``chat`` schema has been migrated (``make migrate``).

A small "best-effort" finalizer deletes the session created during the
test so reruns stay clean — cascade takes the messages with it.
"""

from __future__ import annotations

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
    """Use the real app — no dependency overrides."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@requires_anthropic
async def test_create_session_send_message_returns_assistant_reply(
    live_client: AsyncClient, settings: ChatServiceSettings
) -> None:
    created_sid: UUID | None = None
    sm = get_sessionmaker(settings)

    try:
        created = await live_client.post(
            "/sessions",
            json={
                "title": "e2e",
                "system_prompt": "Answer in exactly one short sentence.",
            },
        )
        assert created.status_code == 201, created.text
        created_body = created.json()
        created_sid = UUID(created_body["id"])

        r = await live_client.post(
            f"/chat/{created_sid}/messages",
            json={"content": "say the word 'pong' and nothing else"},
            timeout=60.0,
        )
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["user_message"]["content"] == "say the word 'pong' and nothing else"
        assert body["user_message"]["role"] == "user"
        assert body["user_message"]["seq"] == 1

        assert body["assistant_message"]["role"] == "assistant"
        assert body["assistant_message"]["seq"] == 2
        assert body["assistant_message"]["content"].strip() != ""

        # Verify persistence directly in Postgres.
        async with sm() as db:
            row_count = await db.scalar(
                text("SELECT COUNT(*) FROM chat.messages WHERE session_id = CAST(:sid AS uuid)"),
                {"sid": str(created_sid)},
            )
            assert row_count == 2
    finally:
        if created_sid is not None:
            async with sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
