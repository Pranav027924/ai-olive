"""End-to-end PDF attachment test (Phase 6.10).

POST /sessions               creates a session with a system prompt
POST /sessions/{id}/files    uploads a PDF carrying a unique sentinel
                             string; chat-service writes the bytes to
                             MinIO, the parse_status row to Postgres,
                             then runs the BackgroundTasks parser
GET  /sessions/{id}          polled until parse_status='complete' so
                             we know the attachment text is available
GET  /chat/{id}/stream       SSE stream; we assert the LLM reply
                             references the sentinel string

Preconditions (skipped automatically if not met):
- ``ANTHROPIC_API_KEY`` is set
- Postgres + MinIO are reachable (``make up`` brings them up)
- ``chat.attachments`` table migrated (``make migrate``)
"""

from __future__ import annotations

import asyncio
import io
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from chat_service.config import ChatServiceSettings
from chat_service.infrastructure.persistence.engine import get_sessionmaker
from chat_service.interfaces.http.app import create_app
from httpx import ASGITransport, AsyncClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import text

requires_anthropic = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live e2e",
)

SENTINEL = f"olive-sentinel-{uuid4().hex[:8]}"


def _build_pdf(sentinel: str) -> bytes:
    buf = io.BytesIO()
    canvas = Canvas(buf)
    canvas.drawString(100, 750, f"My secret code is {sentinel}.")
    canvas.showPage()
    canvas.save()
    return buf.getvalue()


@pytest.fixture
def settings() -> ChatServiceSettings:
    return ChatServiceSettings()


@pytest_asyncio.fixture
async def live_client(settings: ChatServiceSettings) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=60.0
    ) as c:
        yield c


async def _wait_for_complete() -> None:
    """Sleep long enough for the BackgroundTask parser to finish.

    The session view doesn't yet expose attachment status, so the test
    pre-flights with a fixed delay before reading the row directly.
    """
    await asyncio.sleep(2.0)


@requires_anthropic
async def test_pdf_upload_then_streamed_reply_references_sentinel(
    live_client: AsyncClient, settings: ChatServiceSettings
) -> None:
    sm = get_sessionmaker(settings)
    created_sid: UUID | None = None

    try:
        created = await live_client.post(
            "/sessions",
            json={
                "title": "pdf-e2e",
                "system_prompt": (
                    "If the user asks you to repeat their secret code, you must "
                    "reply with exactly the string after 'My secret code is '."
                ),
            },
        )
        assert created.status_code == 201, created.text
        created_sid = UUID(created.json()["id"])

        upload = await live_client.post(
            f"/sessions/{created_sid}/files",
            files={"file": ("secret.pdf", _build_pdf(SENTINEL), "application/pdf")},
        )
        assert upload.status_code == 202, upload.text
        attachment_id = UUID(upload.json()["id"])

        await _wait_for_complete()

        # Confirm parsing actually finished by reading the row directly.
        async with sm() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT parse_status, parsed_text "
                        "FROM chat.attachments WHERE id = CAST(:aid AS uuid)"
                    ),
                    {"aid": str(attachment_id)},
                )
            ).one()
            assert row.parse_status == "complete"
            assert SENTINEL in (row.parsed_text or "")

        await live_client.post(
            f"/chat/{created_sid}/messages", json={"content": "What is my secret code?"}
        )

        chunks: list[str] = []
        async with live_client.stream("GET", f"/chat/{created_sid}/stream") as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    chunks.append(line.removeprefix("data: "))

        reply = "".join(chunks)
        assert SENTINEL in reply, f"sentinel missing from reply: {reply!r}"
    finally:
        if created_sid is not None:
            async with sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
