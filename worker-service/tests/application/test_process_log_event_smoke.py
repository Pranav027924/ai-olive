"""Smoke test for ProcessLogEventHandler (Phase 5.4).

Detailed coverage (duplicates, errors, idempotency interplay) lands in
Phase 5.5.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from contracts.log_event import LogEvent
from worker_service.application.ports.log_repository import LogRepository
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventCommand,
    ProcessLogEventHandler,
)
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.infrastructure.redaction.regex_redactor import default_pipeline


class _InMemoryLogRepository(LogRepository):
    def __init__(self) -> None:
        self.inserted: list[ProcessedLog] = []
        self._ids: set[UUID] = set()

    async def exists(self, event_id: UUID) -> bool:
        return event_id in self._ids

    async def insert(self, processed: ProcessedLog) -> None:
        if processed.id in self._ids:
            raise RuntimeError(f"duplicate id {processed.id}")
        self._ids.add(processed.id)
        self.inserted.append(processed)


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
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "input_preview": "email me at alice@example.com",
        "output_preview": "ok i'll write to alice@example.com",
        "sdk_version": "0.1.0",
    }
    base.update(overrides)
    return LogEvent(**base)  # type: ignore[arg-type]


async def test_handle_inserts_a_redacted_cost_stamped_row() -> None:
    repo = _InMemoryLogRepository()
    handler = ProcessLogEventHandler(
        repo=repo,
        pipeline=default_pipeline(),
        cost_calculator=CostCalculator(),
    )

    ev = _event()
    result = await handler.handle(ProcessLogEventCommand(event=ev))

    assert result.inserted is True
    assert result.processed is not None
    assert result.processed.id == ev.event_id

    assert len(repo.inserted) == 1
    row = repo.inserted[0]
    # Previews are redacted
    assert "alice@example.com" not in row.input_preview
    assert "<email>" in row.input_preview
    assert "alice@example.com" not in row.output_preview
    # Cost is computed (1000 in + 500 out for opus-4-7 = $0.0525)
    assert row.cost_usd == Decimal("0.052500")
