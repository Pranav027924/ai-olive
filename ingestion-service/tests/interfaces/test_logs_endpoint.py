"""Exhaustive HTTP tests for POST /v1/logs (Phase 4.7)."""

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
from ingestion_service.application.use_cases.ingest_logs import IngestLogsHandler
from ingestion_service.domain.services.validator import BatchValidator
from ingestion_service.interfaces.http.app import create_app
from ingestion_service.interfaces.http.dependencies import (
    get_auth_provider,
    get_ingest_logs_handler,
    get_log_stream,
)

KEY = "test-key-abc"


class _InMemoryStream(LogStream):
    def __init__(self) -> None:
        self.payloads: list[dict[str, str]] = []

    async def add(self, payload: dict[str, str]) -> str:
        self.payloads.append(payload)
        return f"0-{len(self.payloads)}"


class _StaticAuth(AuthProvider):
    def __init__(self, *, expected: str) -> None:
        self.expected = expected

    def is_valid(self, api_key: str) -> bool:
        return api_key == self.expected


@pytest.fixture
def stream() -> _InMemoryStream:
    return _InMemoryStream()


@pytest.fixture
def app(stream: _InMemoryStream) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_log_stream] = lambda: stream
    app.dependency_overrides[get_auth_provider] = lambda: _StaticAuth(expected=KEY)
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _event(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
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
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Auth (401)
# ---------------------------------------------------------------------------


async def test_missing_x_api_key_returns_401(client: AsyncClient, stream: _InMemoryStream) -> None:
    r = await client.post("/v1/logs", json={"events": [_event()]})
    assert r.status_code == 401
    assert stream.payloads == []


async def test_wrong_x_api_key_returns_401(client: AsyncClient, stream: _InMemoryStream) -> None:
    r = await client.post("/v1/logs", json={"events": [_event()]}, headers={"x-api-key": "nope"})
    assert r.status_code == 401
    assert stream.payloads == []


async def test_valid_x_api_key_proceeds_to_202(
    client: AsyncClient, stream: _InMemoryStream
) -> None:
    r = await client.post("/v1/logs", json={"events": [_event()]}, headers={"x-api-key": KEY})
    assert r.status_code == 202
    assert len(stream.payloads) == 1


# ---------------------------------------------------------------------------
# Schema validation (422)
# ---------------------------------------------------------------------------


async def test_missing_events_field_is_422(client: AsyncClient) -> None:
    r = await client.post("/v1/logs", json={}, headers={"x-api-key": KEY})
    assert r.status_code == 422


async def test_extra_request_field_is_422(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/logs",
        json={"events": [_event()], "extra": "nope"},
        headers={"x-api-key": KEY},
    )
    assert r.status_code == 422


async def test_invalid_event_field_is_422(client: AsyncClient) -> None:
    bad = _event(provider="cohere")  # not a known provider literal
    r = await client.post("/v1/logs", json={"events": [bad]}, headers={"x-api-key": KEY})
    assert r.status_code == 422


async def test_negative_latency_is_422(client: AsyncClient) -> None:
    bad = _event(latency_ms=-1)
    r = await client.post("/v1/logs", json={"events": [bad]}, headers={"x-api-key": KEY})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Domain validation (400 problem+json)
# ---------------------------------------------------------------------------


async def test_empty_events_list_is_400_problem_json(client: AsyncClient) -> None:
    r = await client.post("/v1/logs", json={"events": []}, headers={"x-api-key": KEY})
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["title"] == "empty batch"


async def test_oversized_batch_is_400_problem_json(
    app: FastAPI, client: AsyncClient, stream: _InMemoryStream
) -> None:
    # Inject a low cap by overriding the handler dep with one that uses a
    # tiny validator.
    app.dependency_overrides[get_ingest_logs_handler] = lambda: IngestLogsHandler(
        stream=stream, validator=BatchValidator(MAX_BATCH_SIZE=1)
    )

    r = await client.post(
        "/v1/logs",
        json={"events": [_event(), _event()]},
        headers={"x-api-key": KEY},
    )
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["title"] == "batch too large"
    assert "2" in body["detail"]
    assert "1" in body["detail"]


# ---------------------------------------------------------------------------
# Happy path (202)
# ---------------------------------------------------------------------------


async def test_valid_batch_returns_202_with_per_event_ids(
    client: AsyncClient, stream: _InMemoryStream
) -> None:
    events = [_event(), _event(), _event()]
    r = await client.post("/v1/logs", json={"events": events}, headers={"x-api-key": KEY})
    assert r.status_code == 202

    body = r.json()
    assert len(body["ingestion_ids"]) == 3
    assert [UUID(i) for i in body["ingestion_ids"]]
    assert body["stream_ids"] == ["0-1", "0-2", "0-3"]
    assert len(stream.payloads) == 3


async def test_single_event_batch_is_accepted(client: AsyncClient, stream: _InMemoryStream) -> None:
    r = await client.post("/v1/logs", json={"events": [_event()]}, headers={"x-api-key": KEY})
    assert r.status_code == 202
    assert len(stream.payloads) == 1
