"""Exhaustive tests for IngestLogsHandler (Phase 4.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from contracts.log_event import LogEvent
from ingestion_service.application.ports.log_stream import LogStream
from ingestion_service.application.use_cases.ingest_logs import (
    IngestLogsCommand,
    IngestLogsHandler,
)
from ingestion_service.domain.errors import BatchTooLarge, EmptyBatch
from ingestion_service.domain.services.validator import BatchValidator

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _InMemoryLogStream(LogStream):
    """Records every XADD payload; can be configured to fail at a given index."""

    def __init__(self, *, fail_at: int | None = None) -> None:
        self.payloads: list[dict[str, str]] = []
        self._next = 0
        self._fail_at = fail_at

    async def add(self, payload: dict[str, str]) -> str:
        if self._fail_at is not None and len(self.payloads) == self._fail_at:
            raise RuntimeError("redis is on fire")
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


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_empty_batch_raises_empty_batch_and_does_not_touch_stream() -> None:
    stream = _InMemoryLogStream()
    handler = IngestLogsHandler(stream=stream)

    with pytest.raises(EmptyBatch):
        await handler.handle(IngestLogsCommand(events=[]))

    assert stream.payloads == []


async def test_oversized_batch_raises_batch_too_large_with_size_and_limit() -> None:
    stream = _InMemoryLogStream()
    validator = BatchValidator(MAX_BATCH_SIZE=3)
    handler = IngestLogsHandler(stream=stream, validator=validator)

    with pytest.raises(BatchTooLarge) as exc:
        await handler.handle(IngestLogsCommand(events=[_event(), _event(), _event(), _event()]))

    assert exc.value.size == 4
    assert exc.value.limit == 3
    assert stream.payloads == []


async def test_batch_at_the_size_limit_is_accepted() -> None:
    stream = _InMemoryLogStream()
    validator = BatchValidator(MAX_BATCH_SIZE=3)
    handler = IngestLogsHandler(stream=stream, validator=validator)

    result = await handler.handle(IngestLogsCommand(events=[_event(), _event(), _event()]))

    assert len(result.ingestion_ids) == 3
    assert len(stream.payloads) == 3


# ---------------------------------------------------------------------------
# Per-event IDs and payload shape
# ---------------------------------------------------------------------------


async def test_ingestion_ids_are_distinct_uuids_per_event() -> None:
    stream = _InMemoryLogStream()
    handler = IngestLogsHandler(stream=stream)

    result = await handler.handle(IngestLogsCommand(events=[_event() for _ in range(10)]))

    assert len(result.ingestion_ids) == 10
    assert all(isinstance(i, UUID) for i in result.ingestion_ids)
    assert len(set(result.ingestion_ids)) == 10


async def test_payload_carries_ingestion_id_and_json_event() -> None:
    stream = _InMemoryLogStream()
    handler = IngestLogsHandler(stream=stream)
    ev = _event()

    result = await handler.handle(IngestLogsCommand(events=[ev]))

    payload = stream.payloads[0]
    assert set(payload) == {"ingestion_id", "event"}
    assert payload["ingestion_id"] == str(result.ingestion_ids[0])
    restored = LogEvent.model_validate_json(payload["event"])
    assert restored == ev


async def test_stream_ids_are_returned_in_event_order() -> None:
    stream = _InMemoryLogStream()
    handler = IngestLogsHandler(stream=stream)

    result = await handler.handle(IngestLogsCommand(events=[_event() for _ in range(4)]))

    assert result.stream_ids == ["0-1", "0-2", "0-3", "0-4"]


# ---------------------------------------------------------------------------
# Mid-batch failure
# ---------------------------------------------------------------------------


async def test_mid_batch_stream_failure_propagates_and_keeps_partial_payloads() -> None:
    """When the stream raises mid-loop the handler propagates the error;
    the events successfully enqueued before the failure remain on the
    stream. Idempotency at the worker (event_id) protects against
    duplicates on retry."""
    stream = _InMemoryLogStream(fail_at=2)
    handler = IngestLogsHandler(stream=stream)

    with pytest.raises(RuntimeError, match="redis is on fire"):
        await handler.handle(IngestLogsCommand(events=[_event() for _ in range(5)]))

    assert len(stream.payloads) == 2


# ---------------------------------------------------------------------------
# Validator independence
# ---------------------------------------------------------------------------


async def test_custom_validator_can_lower_the_batch_cap() -> None:
    stream = _InMemoryLogStream()
    handler = IngestLogsHandler(stream=stream, validator=BatchValidator(MAX_BATCH_SIZE=1))

    with pytest.raises(BatchTooLarge):
        await handler.handle(IngestLogsCommand(events=[_event(), _event()]))


def test_validator_default_max_batch_is_500() -> None:
    assert BatchValidator().MAX_BATCH_SIZE == 500
