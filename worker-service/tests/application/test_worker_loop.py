"""Tests for WorkerLoop (Phase 5.10)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from contracts.log_event import LogEvent
from worker_service.application.ports.log_repository import LogRepository
from worker_service.application.ports.stream_consumer import StreamConsumer, StreamMessage
from worker_service.application.use_cases.process_log_event import ProcessLogEventHandler
from worker_service.application.worker_loop import WorkerLoop
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.domain.services.redaction_pipeline import RedactionPipeline

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _InMemoryConsumer(StreamConsumer):
    """Returns a single pre-scripted batch, then empty for the rest."""

    def __init__(self, batches: list[list[StreamMessage]] | None = None) -> None:
        self._batches: list[list[StreamMessage]] = list(batches or [])
        self.acked: list[str] = []
        self.read_calls: int = 0

    async def read(self, *, max_messages: int, block_ms: int) -> list[StreamMessage]:
        self.read_calls += 1
        await asyncio.sleep(0)  # mirror the real adapter's I/O yield
        if not self._batches:
            return []
        return self._batches.pop(0)

    async def ack(self, message_ids: list[str]) -> None:
        self.acked.extend(message_ids)


class _InMemoryLogRepository(LogRepository):
    def __init__(self, *, raise_on_insert: bool = False) -> None:
        self.inserted: list[ProcessedLog] = []
        self._ids: set[UUID] = set()
        self._raise_on_insert = raise_on_insert

    async def exists(self, event_id: UUID) -> bool:
        return event_id in self._ids

    async def insert(self, processed: ProcessedLog) -> None:
        if self._raise_on_insert:
            raise RuntimeError("simulated postgres outage")
        self._ids.add(processed.id)
        self.inserted.append(processed)


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


def _message(event: LogEvent, message_id: str) -> StreamMessage:
    return StreamMessage(
        message_id=message_id,
        payload={"ingestion_id": str(uuid4()), "event": event.model_dump_json()},
    )


def _handler(repo: LogRepository) -> ProcessLogEventHandler:
    return ProcessLogEventHandler(
        repo=repo,
        pipeline=RedactionPipeline(),
        cost_calculator=CostCalculator(),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_run_once_processes_and_acks_every_message() -> None:
    ev_a, ev_b = _event(), _event()
    consumer = _InMemoryConsumer([[_message(ev_a, "0-1"), _message(ev_b, "0-2")]])
    repo = _InMemoryLogRepository()
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))

    processed = await loop.run_once()

    assert processed == 2
    assert consumer.acked == ["0-1", "0-2"]
    assert [r.id for r in repo.inserted] == [ev_a.event_id, ev_b.event_id]


async def test_empty_batch_returns_zero_and_acks_nothing() -> None:
    consumer = _InMemoryConsumer([])
    repo = _InMemoryLogRepository()
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))
    assert await loop.run_once() == 0
    assert consumer.acked == []


# ---------------------------------------------------------------------------
# Failure semantics
# ---------------------------------------------------------------------------


async def test_poison_payload_is_acked_but_not_inserted() -> None:
    """A pydantic ValidationError on the inbound payload is a poison
    message — ack it so it doesn't redeliver forever."""
    bad = StreamMessage(message_id="0-1", payload={"event": "{not json}"})
    consumer = _InMemoryConsumer([[bad]])
    repo = _InMemoryLogRepository()
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))

    processed = await loop.run_once()

    assert processed == 1
    assert consumer.acked == ["0-1"]
    assert repo.inserted == []


async def test_handler_exception_does_not_ack_so_redelivery_occurs() -> None:
    """If the handler raises (e.g. Postgres outage), the message stays
    un-acked so the consumer-group redelivers."""
    consumer = _InMemoryConsumer([[_message(_event(), "0-1")]])
    repo = _InMemoryLogRepository(raise_on_insert=True)
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))

    processed = await loop.run_once()

    assert processed == 0
    assert consumer.acked == []


async def test_mixed_batch_only_acks_the_successful_ones() -> None:
    good = _message(_event(), "0-1")
    bad = StreamMessage(message_id="0-2", payload={"event": "garbage"})
    consumer = _InMemoryConsumer([[good, bad]])
    repo = _InMemoryLogRepository()
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))

    processed = await loop.run_once()

    # Both ack because both are "terminal" — bad is poison-acked, good is
    # processed-acked.
    assert processed == 2
    assert set(consumer.acked) == {"0-1", "0-2"}
    assert len(repo.inserted) == 1


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


async def test_run_forever_exits_when_shutdown_is_signalled() -> None:
    consumer = _InMemoryConsumer([[_message(_event(), "0-1")]])
    repo = _InMemoryLogRepository()
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))

    async def _stop_after_one_batch() -> None:
        # Give the loop a chance to drain the first batch, then shut down.
        await asyncio.sleep(0.05)
        loop.shutdown()

    await asyncio.gather(loop.run_forever(), _stop_after_one_batch())

    assert consumer.acked == ["0-1"]


async def test_run_forever_keeps_polling_until_shutdown() -> None:
    """An empty stream returns immediately; the loop keeps calling read()
    until ``shutdown()`` flips the event."""
    consumer = _InMemoryConsumer([])
    repo = _InMemoryLogRepository()
    loop = WorkerLoop(consumer=consumer, handler=_handler(repo))

    async def _stop() -> None:
        await asyncio.sleep(0.05)
        loop.shutdown()

    await asyncio.gather(loop.run_forever(), _stop())

    assert consumer.read_calls >= 1
    assert consumer.acked == []
