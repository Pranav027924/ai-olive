"""Smoke test for IngestLogsHandler (Phase 4.2).

Locks in the public surface: every event in the batch becomes one
record in the LogStream and one ingestion_id in the result. Edge
cases (empty batch, oversized batch, mid-batch failures) land in
Phase 4.3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from contracts.log_event import LogEvent
from ingestion_service.application.ports.log_stream import LogStream
from ingestion_service.application.use_cases.ingest_logs import (
    IngestLogsCommand,
    IngestLogsHandler,
)


class _InMemoryLogStream(LogStream):
    def __init__(self) -> None:
        self.payloads: list[dict[str, str]] = []
        self._next = 0

    async def add(self, payload: dict[str, str]) -> str:
        self.payloads.append(payload)
        self._next += 1
        return f"0-{self._next}"


def _event(**overrides: object) -> LogEvent:
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


async def test_handle_enqueues_one_record_per_event_and_returns_ids() -> None:
    stream = _InMemoryLogStream()
    handler = IngestLogsHandler(stream=stream)

    events = [_event(), _event(), _event()]
    result = await handler.handle(IngestLogsCommand(events=events))

    assert len(result.ingestion_ids) == 3
    assert all(isinstance(i, UUID) for i in result.ingestion_ids)
    assert result.stream_ids == ["0-1", "0-2", "0-3"]
    assert len(stream.payloads) == 3

    # Each payload carries the JSON-encoded event + the ingestion_id.
    for payload, ev, ingest_id in zip(stream.payloads, events, result.ingestion_ids, strict=True):
        assert payload["ingestion_id"] == str(ingest_id)
        restored = LogEvent.model_validate_json(payload["event"])
        assert restored == ev
