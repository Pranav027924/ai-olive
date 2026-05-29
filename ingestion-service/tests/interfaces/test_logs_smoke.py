"""Smoke test for POST /v1/logs (Phase 4.6).

Detailed coverage of 202 / 401 / 422 / 400 paths lands in 4.7.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from ingestion_service.application.ports.auth_provider import AuthProvider
from ingestion_service.application.ports.log_stream import LogStream
from ingestion_service.interfaces.http.app import create_app
from ingestion_service.interfaces.http.dependencies import (
    get_auth_provider,
    get_log_stream,
)


class _InMemoryStream(LogStream):
    def __init__(self) -> None:
        self.payloads: list[dict[str, str]] = []

    async def add(self, payload: dict[str, str]) -> str:
        self.payloads.append(payload)
        return f"0-{len(self.payloads)}"


class _AlwaysOkAuth(AuthProvider):
    def is_valid(self, api_key: str) -> bool:
        return True


@pytest.fixture
def stream() -> _InMemoryStream:
    return _InMemoryStream()


@pytest.fixture
def app(stream: _InMemoryStream) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_log_stream] = lambda: stream
    app.dependency_overrides[get_auth_provider] = lambda: _AlwaysOkAuth()
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _event() -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "session_id": str(uuid4()),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "status": "success",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "finished_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC).isoformat(),
        "latency_ms": 1000,
        "input_preview": "hi",
        "output_preview": "hello",
        "sdk_version": "0.1.0",
    }


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_valid_batch_returns_202_and_enqueues(
    client: AsyncClient, stream: _InMemoryStream
) -> None:
    body = {"events": [_event(), _event()]}
    r = await client.post("/v1/logs", json=body, headers={"x-api-key": "k"})

    assert r.status_code == 202, r.text
    data = r.json()
    assert len(data["ingestion_ids"]) == 2
    assert [UUID(i) for i in data["ingestion_ids"]]
    assert data["stream_ids"] == ["0-1", "0-2"]
    assert len(stream.payloads) == 2
