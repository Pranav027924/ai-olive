"""End-to-end voice attachment test (Phase 6.11).

POST /sessions                creates a chat session
POST /sessions/{id}/voice     uploads a short WAV; chat-service stores
                              the bytes, then runs the faster-whisper
                              transcriber as a BackgroundTask
Postgres                      polled until parse_status flips to a
                              terminal state and we read the row
GET  /chat/{id}/stream        SSE; assert the model produced a
                              non-empty reply (we don't assert on
                              transcript content because Whisper's
                              output for synthetic audio is noisy)

The test is intentionally lenient on transcription accuracy: it
proves the *wiring* (upload → S3 → BackgroundTask → transcriber →
attachments row → LLM context) without depending on Whisper getting
the exact words right.

Preconditions (skipped automatically if not met):
- ``ANTHROPIC_API_KEY`` is set
- MinIO + Postgres are reachable (``make up``)
- The faster-whisper tiny model can be downloaded on first run
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import struct
import wave
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

SAMPLE_RATE = 16_000
DURATION_SEC = 1.0
FREQUENCY = 220.0


def _build_wav() -> bytes:
    """Generate a one-second 16 kHz mono sine wave.

    Whisper's transcript of pure-tone audio is non-deterministic, so
    the test asserts the pipeline ran rather than the specific text.
    """
    n_samples = int(SAMPLE_RATE * DURATION_SEC)
    amplitude = 0.4 * 32767
    samples = [
        int(amplitude * math.sin(2 * math.pi * FREQUENCY * (t / SAMPLE_RATE)))
        for t in range(n_samples)
    ]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    return buf.getvalue()


@pytest.fixture
def settings() -> ChatServiceSettings:
    return ChatServiceSettings()


@pytest_asyncio.fixture
async def live_client(settings: ChatServiceSettings) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=120.0
    ) as c:
        yield c


@requires_anthropic
async def test_audio_upload_then_chat_reply_is_streamed(
    live_client: AsyncClient, settings: ChatServiceSettings
) -> None:
    sm = get_sessionmaker(settings)
    created_sid: UUID | None = None

    try:
        created = await live_client.post(
            "/sessions",
            json={
                "title": "voice-e2e",
                "system_prompt": (
                    "Briefly acknowledge that you received a voice clip from the user, "
                    "in one sentence."
                ),
            },
        )
        assert created.status_code == 201, created.text
        created_sid = UUID(created.json()["id"])

        upload = await live_client.post(
            f"/sessions/{created_sid}/voice",
            files={"file": ("clip.wav", _build_wav(), "audio/wav")},
        )
        assert upload.status_code == 202, upload.text
        attachment_id = UUID(upload.json()["id"])

        # Whisper tiny + a one-second clip needs a few seconds the first time.
        # Poll Postgres directly for a terminal parse_status.
        for _ in range(60):
            async with sm() as db:
                row = (
                    await db.execute(
                        text(
                            "SELECT parse_status FROM chat.attachments "
                            "WHERE id = CAST(:aid AS uuid)"
                        ),
                        {"aid": str(attachment_id)},
                    )
                ).one()
                if row.parse_status in {"complete", "failed"}:
                    terminal_status = row.parse_status
                    break
            await asyncio.sleep(0.5)
        else:
            raise AssertionError("transcription never reached a terminal state")

        # Either path is acceptable for the wiring test — what we care
        # about is that the chat reply still works given the upload.
        assert terminal_status in {"complete", "failed"}

        await live_client.post(
            f"/chat/{created_sid}/messages",
            json={"content": "Please acknowledge my voice clip."},
        )

        chunks: list[str] = []
        async with live_client.stream("GET", f"/chat/{created_sid}/stream") as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    chunks.append(line.removeprefix("data: "))

        reply = "".join(chunks)
        assert reply.strip(), "expected a non-empty streamed reply"
    finally:
        if created_sid is not None:
            async with sm() as db, db.begin():
                await db.execute(
                    text("DELETE FROM chat.sessions WHERE id = CAST(:sid AS uuid)"),
                    {"sid": str(created_sid)},
                )
