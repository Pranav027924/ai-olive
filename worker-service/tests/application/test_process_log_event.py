"""Exhaustive tests for ProcessLogEventHandler (Phase 5.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from contracts.log_event import LogEvent
from worker_service.application.ports.log_repository import LogRepository
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventCommand,
    ProcessLogEventHandler,
)
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.domain.services.idempotency_checker import IdempotencyChecker
from worker_service.domain.services.redaction_pipeline import RedactionPipeline
from worker_service.infrastructure.redaction.regex_redactor import default_pipeline

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _InMemoryLogRepository(LogRepository):
    def __init__(self) -> None:
        self.inserted: list[ProcessedLog] = []
        self._ids: set[UUID] = set()
        self.exists_calls: list[UUID] = []
        self.insert_calls: list[UUID] = []

    async def exists(self, event_id: UUID) -> bool:
        self.exists_calls.append(event_id)
        return event_id in self._ids

    async def insert(self, processed: ProcessedLog) -> None:
        self.insert_calls.append(processed.id)
        if processed.id in self._ids:
            raise RuntimeError(f"duplicate id {processed.id}")
        self._ids.add(processed.id)
        self.inserted.append(processed)

    def seed(self, event_id: UUID) -> None:
        self._ids.add(event_id)


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
        "input_preview": "hi",
        "output_preview": "hello",
        "sdk_version": "0.1.0",
    }
    base.update(overrides)
    return LogEvent(**base)  # type: ignore[arg-type]


def _handler(
    repo: _InMemoryLogRepository,
    *,
    pipeline: RedactionPipeline | None = None,
    idempotency: IdempotencyChecker | None = None,
) -> ProcessLogEventHandler:
    return ProcessLogEventHandler(
        repo=repo,
        pipeline=pipeline or default_pipeline(),
        cost_calculator=CostCalculator(),
        idempotency=idempotency,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_happy_path_inserts_and_returns_processed_log() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)

    result = await handler.handle(ProcessLogEventCommand(event=_event()))

    assert result.inserted is True
    assert result.processed is not None
    assert len(repo.inserted) == 1
    assert repo.inserted[0].id == result.processed.id


async def test_previews_are_redacted_before_insert() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)

    await handler.handle(
        ProcessLogEventCommand(
            event=_event(
                input_preview="contact alice@example.com please",
                output_preview="ok, mail bob@example.com",
            )
        )
    )

    row = repo.inserted[0]
    assert "alice@example.com" not in row.input_preview
    assert "<email>" in row.input_preview
    assert "bob@example.com" not in row.output_preview
    assert "<email>" in row.output_preview


async def test_cost_is_recomputed_from_token_counts() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)
    # opus-4-7: 1M in = $15, 1M out = $75. So 1k in + 500 out = $0.0525.
    await handler.handle(
        ProcessLogEventCommand(event=_event(prompt_tokens=1000, completion_tokens=500))
    )
    assert repo.inserted[0].cost_usd == Decimal("0.052500")


async def test_unknown_model_yields_null_cost() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)
    await handler.handle(ProcessLogEventCommand(event=_event(model="claude-of-the-future")))
    assert repo.inserted[0].cost_usd is None


async def test_idempotency_cache_is_marked_on_first_insert() -> None:
    repo = _InMemoryLogRepository()
    cache = IdempotencyChecker()
    handler = _handler(repo, idempotency=cache)

    ev = _event()
    await handler.handle(ProcessLogEventCommand(event=ev))
    assert cache.is_known(ev.event_id) is True
    assert cache.size() == 1


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------


async def test_cache_hit_short_circuits_without_touching_repo() -> None:
    repo = _InMemoryLogRepository()
    cache = IdempotencyChecker()
    handler = _handler(repo, idempotency=cache)

    ev = _event()
    cache.mark(ev.event_id)

    result = await handler.handle(ProcessLogEventCommand(event=ev))
    assert result.inserted is False
    assert result.processed is None
    assert repo.exists_calls == []
    assert repo.insert_calls == []


async def test_repo_hit_marks_cache_and_skips_insert() -> None:
    repo = _InMemoryLogRepository()
    cache = IdempotencyChecker()
    handler = _handler(repo, idempotency=cache)

    ev = _event()
    repo.seed(ev.event_id)

    result = await handler.handle(ProcessLogEventCommand(event=ev))
    assert result.inserted is False
    assert repo.exists_calls == [ev.event_id]
    assert repo.insert_calls == []
    assert cache.is_known(ev.event_id) is True


async def test_second_delivery_same_handler_is_a_cache_hit() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)

    ev = _event()
    first = await handler.handle(ProcessLogEventCommand(event=ev))
    second = await handler.handle(ProcessLogEventCommand(event=ev))

    assert first.inserted is True
    assert second.inserted is False
    assert len(repo.inserted) == 1
    # The cache should have short-circuited the second call before the
    # repo lookup.
    assert repo.exists_calls == [ev.event_id]


# ---------------------------------------------------------------------------
# Error events
# ---------------------------------------------------------------------------


async def test_error_event_inserts_processed_log_with_error_fields_set() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)
    ev = _event(
        status="error",
        error_type="ProviderTimeout",
        error_message="upstream 504",
        http_status=504,
        # Errors often have no usage from the provider.
        prompt_tokens=None,
        completion_tokens=None,
    )

    result = await handler.handle(ProcessLogEventCommand(event=ev))
    assert result.inserted is True
    row = repo.inserted[0]
    assert row.status == "error"
    assert row.error_type == "ProviderTimeout"
    assert row.error_message == "upstream 504"
    assert row.http_status == 504
    assert row.has_error is True
    assert row.cost_usd == Decimal("0")  # zero tokens → zero cost


async def test_cancelled_event_does_not_set_error_fields() -> None:
    repo = _InMemoryLogRepository()
    handler = _handler(repo)
    ev = _event(status="cancelled")

    await handler.handle(ProcessLogEventCommand(event=ev))
    row = repo.inserted[0]
    assert row.status == "cancelled"
    assert row.error_type is None
    assert row.has_error is False


# ---------------------------------------------------------------------------
# Pipeline + cost wiring
# ---------------------------------------------------------------------------


async def test_custom_pipeline_is_honoured() -> None:
    """A pipeline with no redactors leaves previews untouched."""
    repo = _InMemoryLogRepository()
    handler = _handler(repo, pipeline=RedactionPipeline())
    await handler.handle(
        ProcessLogEventCommand(event=_event(input_preview="alice@example.com", output_preview="x"))
    )
    assert repo.inserted[0].input_preview == "alice@example.com"


async def test_handle_propagates_repo_insert_failures() -> None:
    """Insert errors bubble up so the caller (worker loop) can avoid acking."""
    repo = _InMemoryLogRepository()

    class _BoomRepo(_InMemoryLogRepository):
        async def insert(self, processed: ProcessedLog) -> None:
            raise RuntimeError("simulated postgres outage")

    handler = _handler(_BoomRepo())
    with pytest.raises(RuntimeError, match="simulated postgres outage"):
        await handler.handle(ProcessLogEventCommand(event=_event()))
    assert repo.inserted == []
