"""Smoke test: LogEvent must exist with the shape declared in PRD §7.1.

This test is intentionally minimal — it locks in the public surface of
LogEvent so subsequent commits cannot accidentally rename or remove a
field without breaking CI. Detailed validation behavior is covered in
``test_log_event_validation.py`` (Phase 0.5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from contracts.log_event import LogEvent


def _minimal_kwargs() -> dict[str, object]:
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
    return {
        "event_id": uuid4(),
        "session_id": uuid4(),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "status": "success",
        "started_at": started,
        "finished_at": finished,
        "latency_ms": 1000,
        "input_preview": "hello",
        "output_preview": "world",
        "sdk_version": "0.1.0",
    }


def test_log_event_constructs_with_required_fields_only() -> None:
    event = LogEvent(**_minimal_kwargs())  # type: ignore[arg-type]

    assert isinstance(event.event_id, UUID)
    assert isinstance(event.session_id, UUID)
    assert event.message_id is None
    assert event.provider == "anthropic"
    assert event.model == "claude-opus-4-7"
    assert event.status == "success"
    assert event.latency_ms == 1000
    assert event.ttft_ms is None
    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.input_preview == "hello"
    assert event.output_preview == "world"
    assert event.error_type is None
    assert event.error_message is None
    assert event.http_status is None
    assert event.raw_metadata == {}
    assert event.sdk_version == "0.1.0"


def test_log_event_round_trips_through_json() -> None:
    event = LogEvent(**_minimal_kwargs())  # type: ignore[arg-type]

    payload = event.model_dump_json()
    restored = LogEvent.model_validate_json(payload)

    assert restored == event
