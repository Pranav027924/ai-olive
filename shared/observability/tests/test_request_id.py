"""Tests for RequestIdMiddleware (Phase 9.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from olive_obs.request_id import REQUEST_ID_HEADER, RequestIdMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str | None]:
        bound = structlog.contextvars.get_contextvars().get("request_id")
        return {"bound_request_id": bound}

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            for i in range(3):
                yield f"chunk-{i}\n"

        return StreamingResponse(gen(), media_type="text/plain")

    return app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test")


async def test_generates_request_id_when_absent() -> None:
    async with _client() as client:
        response = await client.get("/ping")
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]
    assert response.json()["bound_request_id"] == response.headers[REQUEST_ID_HEADER]


async def test_echoes_incoming_request_id() -> None:
    async with _client() as client:
        response = await client.get("/ping", headers={REQUEST_ID_HEADER: "trace-abc"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc"
    assert response.json()["bound_request_id"] == "trace-abc"


async def test_contextvars_cleared_between_requests() -> None:
    async with _client() as client:
        first = await client.get("/ping", headers={REQUEST_ID_HEADER: "first"})
        second = await client.get("/ping")
    assert first.json()["bound_request_id"] == "first"
    assert second.json()["bound_request_id"] != "first"


async def test_streaming_response_still_carries_header() -> None:
    """A pure-ASGI middleware must not buffer the body: the streamed
    chunks arrive intact and the header is still stamped."""
    async with _client() as client:
        response = await client.get("/stream")
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]
    assert response.text == "chunk-0\nchunk-1\nchunk-2\n"
