"""Integration test: ProcessLogEventHandler routes successful inserts to MetricsSink (Phase 7.6)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from contracts.log_event import LogEvent
from worker_service.application.ports.log_repository import LogRepository
from worker_service.application.ports.metrics_sink import MetricsSink
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventCommand,
    ProcessLogEventHandler,
)
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.domain.services.redaction_pipeline import RedactionPipeline


class _InMemoryRepo(LogRepository):
    def __init__(self) -> None:
        self._ids: set[UUID] = set()
        self.inserted: list[ProcessedLog] = []

    async def exists(self, event_id: UUID) -> bool:
        return event_id in self._ids

    async def insert(self, processed: ProcessedLog) -> None:
        self._ids.add(processed.id)
        self.inserted.append(processed)


class _RecordingSink(MetricsSink):
    def __init__(self, *, raise_on_record: bool = False) -> None:
        self.records: list[ProcessedLog] = []
        self.flushed = 0
        self.closed = 0
        self._raise_on_record = raise_on_record

    async def record(self, processed: ProcessedLog) -> None:
        if self._raise_on_record:
            raise RuntimeError("sink down")
        self.records.append(processed)

    async def flush(self) -> None:
        self.flushed += 1

    async def close(self) -> None:
        self.closed += 1


def _event() -> LogEvent:
    return LogEvent(
        event_id=uuid4(),
        session_id=uuid4(),
        provider="anthropic",
        model="claude-opus-4-7",
        status="success",
        started_at=datetime(2026, 6, 1, tzinfo=UTC),
        finished_at=datetime(2026, 6, 1, 0, 0, 1, tzinfo=UTC),
        latency_ms=1000,
        input_preview="hi",
        output_preview="hello",
        sdk_version="0.1.0",
    )


def _handler(*, repo: LogRepository, sink: MetricsSink) -> ProcessLogEventHandler:
    return ProcessLogEventHandler(
        repo=repo,
        pipeline=RedactionPipeline(),
        cost_calculator=CostCalculator(),
        metrics_sink=sink,
    )


async def test_successful_insert_also_records_into_metrics_sink() -> None:
    repo = _InMemoryRepo()
    sink = _RecordingSink()
    handler = _handler(repo=repo, sink=sink)

    await handler.handle(ProcessLogEventCommand(event=_event()))

    assert len(repo.inserted) == 1
    assert len(sink.records) == 1
    assert sink.records[0].id == repo.inserted[0].id


async def test_duplicate_event_does_not_record_a_second_time() -> None:
    repo = _InMemoryRepo()
    sink = _RecordingSink()
    handler = _handler(repo=repo, sink=sink)

    event = _event()
    await handler.handle(ProcessLogEventCommand(event=event))
    await handler.handle(ProcessLogEventCommand(event=event))

    assert len(sink.records) == 1


async def test_metrics_sink_failure_does_not_roll_back_postgres_insert(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Phase 7.5 contract: analytics is a best-effort mirror. The
    Postgres write has already committed by the time we call the sink."""
    repo = _InMemoryRepo()
    handler = _handler(repo=repo, sink=_RecordingSink(raise_on_record=True))

    with caplog.at_level("ERROR"):
        result = await handler.handle(ProcessLogEventCommand(event=_event()))

    assert result.inserted is True
    assert len(repo.inserted) == 1
    assert any("metrics sink" in r.message for r in caplog.records)
