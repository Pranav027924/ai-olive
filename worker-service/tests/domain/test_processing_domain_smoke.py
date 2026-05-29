"""Smoke test for the worker's domain types (Phase 5.2).

Exhaustive redaction coverage lands in Phase 5.3; this file just
proves the public surface is wired correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from contracts.log_event import LogEvent
from worker_service.domain.entities.processed_log import ProcessedLog
from worker_service.domain.services.cost_calculator import CostCalculator
from worker_service.domain.services.idempotency_checker import IdempotencyChecker
from worker_service.domain.services.redaction_pipeline import RedactionPipeline
from worker_service.infrastructure.redaction.regex_redactor import (
    default_pipeline,
    email_redactor,
)


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
        "input_preview": "ask alice@example.com to call",
        "output_preview": "I'll email alice@example.com",
        "sdk_version": "0.1.0",
    }
    base.update(overrides)
    return LogEvent(**base)  # type: ignore[arg-type]


def test_redaction_pipeline_chains_redactors_in_order() -> None:
    pipe = RedactionPipeline(redactors=(email_redactor(),))
    assert pipe.redact("contact me at bob@host.io now") == "contact me at <email> now"


def test_default_pipeline_handles_an_email() -> None:
    out = default_pipeline().redact("hi alice@example.com, see you")
    assert "<email>" in out
    assert "alice@example.com" not in out


def test_idempotency_checker_tracks_seen_ids() -> None:
    ck = IdempotencyChecker()
    eid = uuid4()
    assert ck.is_known(eid) is False
    ck.mark(eid)
    assert ck.is_known(eid) is True
    assert ck.size() == 1


def test_cost_calculator_returns_decimal_for_known_model() -> None:
    calc = CostCalculator()
    cost = calc.estimate(
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert isinstance(cost, Decimal)
    assert cost > Decimal("0")


def test_processed_log_round_trip_from_event() -> None:
    ev = _event()
    pl = ProcessedLog.from_event(
        ev,
        redacted_input_preview="ask <email> to call",
        redacted_output_preview="I'll email <email>",
        cost_usd=Decimal("0.001"),
    )
    assert isinstance(pl.id, UUID)
    assert pl.id == ev.event_id
    assert pl.session_id == ev.session_id
    assert pl.input_preview == "ask <email> to call"
    assert pl.output_preview == "I'll email <email>"
    assert pl.cost_usd == Decimal("0.001")
    assert pl.has_error is False


def test_processed_log_has_error_when_event_status_error() -> None:
    ev = _event(status="error", error_type="ProviderError", error_message="503")
    pl = ProcessedLog.from_event(
        ev,
        redacted_input_preview="...",
        redacted_output_preview="...",
        cost_usd=None,
    )
    assert pl.has_error is True
    assert pl.error_type == "ProviderError"
    assert pl.error_message == "503"
