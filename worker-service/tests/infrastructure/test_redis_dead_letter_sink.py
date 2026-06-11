"""Tests for RedisDeadLetterSink (Phase 9.6).

Uses a fake redis that records xadd calls so the test runs without a
real Redis instance.
"""

from __future__ import annotations

from typing import Any

from worker_service.application.ports.stream_consumer import StreamMessage
from worker_service.infrastructure.streams.redis_dead_letter_sink import (
    RedisDeadLetterSink,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    async def xadd(self, name: str, fields: dict[str, str], **kwargs: Any) -> str:
        self.calls.append((name, fields, kwargs))
        return f"0-{len(self.calls)}"


def _message() -> StreamMessage:
    return StreamMessage(
        message_id="42-7",
        payload={"event": "{bad json}", "ingestion_id": "ing-1"},
    )


async def test_send_xadds_payload_plus_diagnostics_to_dlq_stream() -> None:
    redis = _FakeRedis()
    sink = RedisDeadLetterSink(redis=redis, stream="dlq", maxlen=500)  # type: ignore[arg-type]

    await sink.send(_message(), reason="ValidationError: boom")

    assert len(redis.calls) == 1
    name, fields, _kwargs = redis.calls[0]
    assert name == "dlq"
    # Original payload is preserved…
    assert fields["event"] == "{bad json}"
    assert fields["ingestion_id"] == "ing-1"
    # …plus diagnostics.
    assert fields["dlq_reason"] == "ValidationError: boom"
    assert fields["dlq_source_id"] == "42-7"
    assert "dlq_at" in fields


async def test_send_applies_approximate_maxlen_trim() -> None:
    redis = _FakeRedis()
    sink = RedisDeadLetterSink(redis=redis, stream="dlq", maxlen=123)  # type: ignore[arg-type]

    await sink.send(_message(), reason="x")

    _, _, kwargs = redis.calls[0]
    assert kwargs["maxlen"] == 123
    assert kwargs["approximate"] is True
