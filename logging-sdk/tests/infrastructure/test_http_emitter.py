"""Tests for HttpEmitter (Phase 4.8).

Drives the emitter against an in-process httpx.ASGIApp (a tiny
ASGI handler we hand-roll here) so we can inspect every POST body
and force status codes / errors deterministically.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from contracts.log_event import LogEvent
from olive_sdk.infrastructure.emitters.http_emitter import HttpEmitter


class _ScriptedEndpoint:
    """ASGI handler that records POST bodies and returns scripted status codes.

    Pass ``status_sequence=[202, 500, 202]`` to make successive calls
    return those codes in order; the last code repeats once the script
    runs out. ``raise_count`` simulates network errors before any
    scripted status code is returned.
    """

    def __init__(
        self,
        *,
        status_sequence: list[int] | None = None,
        raise_count: int = 0,
    ) -> None:
        self.status_sequence = status_sequence or [202]
        self.raise_count = raise_count
        self.received_bodies: list[dict[str, Any]] = []
        self.received_headers: list[dict[str, str]] = []
        self._call_index = 0

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        assert scope["type"] == "http"
        # Collect request body
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        raw = b"".join(body_chunks).decode() if body_chunks else "{}"
        self.received_bodies.append(json.loads(raw))
        self.received_headers.append({k.decode(): v.decode() for k, v in scope.get("headers", [])})

        if self.raise_count > 0:
            self.raise_count -= 1
            # Closing the connection without responding triggers httpx errors.
            raise RuntimeError("simulated network error")

        idx = min(self._call_index, len(self.status_sequence) - 1)
        self._call_index += 1
        status = self.status_sequence[idx]

        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _make_event(**overrides: object) -> LogEvent:
    base: dict[str, object] = {
        "event_id": uuid4(),
        "session_id": uuid4(),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "status": "success",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "finished_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "latency_ms": 1000,
        "input_preview": "hi",
        "output_preview": "hello",
        "sdk_version": "0.1.0",
    }
    base.update(overrides)
    return LogEvent(**base)  # type: ignore[arg-type]


def _client(endpoint: _ScriptedEndpoint) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=endpoint)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://t")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_single_event_is_posted_in_one_batch() -> None:
    endpoint = _ScriptedEndpoint()
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=0.05,
        max_batch=20,
        client=_client(endpoint),
    )
    try:
        await emitter.emit(_make_event())
        # Let the worker pick up the event and flush.
        await asyncio.sleep(0.2)
        assert len(endpoint.received_bodies) == 1
        assert len(endpoint.received_bodies[0]["events"]) == 1
        assert endpoint.received_headers[0].get("x-api-key") == "k"
        assert emitter.delivered_count == 1
    finally:
        await emitter.aclose()


async def test_multiple_events_within_flush_interval_become_one_batch() -> None:
    endpoint = _ScriptedEndpoint()
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=0.2,
        max_batch=50,
        client=_client(endpoint),
    )
    try:
        for _ in range(5):
            await emitter.emit(_make_event())
        await asyncio.sleep(0.4)
        assert len(endpoint.received_bodies) == 1
        assert len(endpoint.received_bodies[0]["events"]) == 5
    finally:
        await emitter.aclose()


async def test_max_batch_caps_a_single_post() -> None:
    endpoint = _ScriptedEndpoint()
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=0.2,
        max_batch=3,
        client=_client(endpoint),
    )
    try:
        for _ in range(7):
            await emitter.emit(_make_event())
        await asyncio.sleep(0.6)
        sizes = [len(b["events"]) for b in endpoint.received_bodies]
        assert sum(sizes) == 7
        assert max(sizes) <= 3
    finally:
        await emitter.aclose()


# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------


async def test_5xx_triggers_retry_until_success() -> None:
    endpoint = _ScriptedEndpoint(status_sequence=[503, 503, 202])
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=0.05,
        max_retries=5,
        initial_backoff_seconds=0.0,
        client=_client(endpoint),
    )
    try:
        await emitter.emit(_make_event())
        await asyncio.sleep(0.5)
        # Three attempts total, only one success counted.
        assert len(endpoint.received_bodies) == 3
        assert emitter.delivered_count == 1
        assert emitter.failed_batches == 0
    finally:
        await emitter.aclose()


async def test_4xx_does_not_retry() -> None:
    endpoint = _ScriptedEndpoint(status_sequence=[400, 400])
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=0.05,
        max_retries=5,
        initial_backoff_seconds=0.0,
        client=_client(endpoint),
    )
    try:
        await emitter.emit(_make_event())
        await asyncio.sleep(0.3)
        assert len(endpoint.received_bodies) == 1
        assert emitter.failed_batches == 1
        assert emitter.delivered_count == 0
    finally:
        await emitter.aclose()


async def test_exhausted_retries_marks_batch_failed() -> None:
    endpoint = _ScriptedEndpoint(status_sequence=[500])
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=0.05,
        max_retries=2,
        initial_backoff_seconds=0.0,
        client=_client(endpoint),
    )
    try:
        await emitter.emit(_make_event())
        await asyncio.sleep(0.5)
        # 1 initial + 2 retries = 3 attempts, none succeed.
        assert len(endpoint.received_bodies) == 3
        assert emitter.failed_batches == 1
        assert emitter.delivered_count == 0
    finally:
        await emitter.aclose()


# ---------------------------------------------------------------------------
# Bounded queue
# ---------------------------------------------------------------------------


async def test_full_queue_drops_events_silently() -> None:
    # Worker can't drain because we never wait — fill the queue past size.
    endpoint = _ScriptedEndpoint()
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        queue_size=3,
        flush_interval_seconds=10.0,  # don't drain during the burst
        client=_client(endpoint),
    )
    try:
        for _ in range(10):
            await emitter.emit(_make_event())
        # 3 queued, 7 dropped.
        assert emitter.dropped_count == 7
    finally:
        await emitter.aclose()


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------


async def test_aclose_drains_pending_events() -> None:
    endpoint = _ScriptedEndpoint()
    emitter = HttpEmitter(
        endpoint="http://t/v1/logs",
        api_key="k",
        flush_interval_seconds=5.0,  # without close() the events would sit
        max_batch=50,
        client=_client(endpoint),
    )
    for _ in range(4):
        await emitter.emit(_make_event())

    await emitter.aclose()
    # The worker drains remaining items before exiting.
    assert len(endpoint.received_bodies) == 1
    assert len(endpoint.received_bodies[0]["events"]) == 4
    assert emitter.delivered_count == 4
