"""Exhaustive validation tests for LogEvent (PRD §7.1, Phase 0.5).

Covers:
- every required field is enforced
- every optional field defaults correctly and accepts a value
- value constraints (literals, length caps, non-negative numbers)
- ``extra="forbid"`` rejects unknown fields
- ``frozen=True`` rejects mutation
- JSON round-trip preserves every field
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from contracts.log_event import PREVIEW_MAX_LENGTH, LogEvent
from pydantic import ValidationError

REQUIRED_FIELDS: tuple[str, ...] = (
    "event_id",
    "session_id",
    "provider",
    "model",
    "status",
    "started_at",
    "finished_at",
    "latency_ms",
    "input_preview",
    "output_preview",
    "sdk_version",
)


def _base_kwargs(**overrides: Any) -> dict[str, Any]:
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    payload: dict[str, Any] = {
        "event_id": uuid4(),
        "session_id": uuid4(),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "status": "success",
        "started_at": started,
        "finished_at": started + timedelta(seconds=1),
        "latency_ms": 1000,
        "input_preview": "hello",
        "output_preview": "world",
        "sdk_version": "0.1.0",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_required_field_is_enforced(field: str) -> None:
    kwargs = _base_kwargs()
    del kwargs[field]

    with pytest.raises(ValidationError) as exc:
        LogEvent(**kwargs)

    missing = {err["loc"][0] for err in exc.value.errors() if err["type"] == "missing"}
    assert field in missing


# ---------------------------------------------------------------------------
# Optional field defaults
# ---------------------------------------------------------------------------


def test_optional_fields_default_correctly() -> None:
    event = LogEvent(**_base_kwargs())

    assert event.message_id is None
    assert event.ttft_ms is None
    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.error_type is None
    assert event.error_message is None
    assert event.http_status is None
    assert event.raw_metadata == {}


def test_optional_fields_accept_values() -> None:
    msg_id = uuid4()
    event = LogEvent(
        **_base_kwargs(
            message_id=msg_id,
            ttft_ms=42,
            prompt_tokens=10,
            completion_tokens=20,
            status="error",
            error_type="ProviderTimeout",
            error_message="upstream timed out",
            http_status=504,
            raw_metadata={"finish_reason": "stop", "system_fingerprint": "fp_abc"},
        )
    )

    assert event.message_id == msg_id
    assert event.ttft_ms == 42
    assert event.prompt_tokens == 10
    assert event.completion_tokens == 20
    assert event.error_type == "ProviderTimeout"
    assert event.error_message == "upstream timed out"
    assert event.http_status == 504
    assert event.raw_metadata == {"finish_reason": "stop", "system_fingerprint": "fp_abc"}


def test_raw_metadata_default_is_independent_per_instance() -> None:
    """Mutable defaults must not be shared (regression: Field(default_factory=dict))."""
    a = LogEvent(**_base_kwargs())
    b = LogEvent(**_base_kwargs())
    # Cannot mutate (frozen), but the underlying dicts must be distinct objects.
    assert a.raw_metadata is not b.raw_metadata


# ---------------------------------------------------------------------------
# Literal constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "deepseek"])
def test_all_documented_providers_are_accepted(provider: str) -> None:
    event = LogEvent(**_base_kwargs(provider=provider))
    assert event.provider == provider


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LogEvent(**_base_kwargs(provider="cohere"))


@pytest.mark.parametrize("status", ["success", "error", "cancelled", "timeout"])
def test_all_documented_statuses_are_accepted(status: str) -> None:
    event = LogEvent(**_base_kwargs(status=status))
    assert event.status == status


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LogEvent(**_base_kwargs(status="partial"))


# ---------------------------------------------------------------------------
# Numeric constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["latency_ms", "ttft_ms", "prompt_tokens", "completion_tokens"])
def test_negative_numeric_field_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError) as exc:
        LogEvent(**_base_kwargs(**{field: -1}))

    bad = {err["loc"][0] for err in exc.value.errors()}
    assert field in bad


def test_zero_latency_is_accepted() -> None:
    event = LogEvent(**_base_kwargs(latency_ms=0))
    assert event.latency_ms == 0


# ---------------------------------------------------------------------------
# Preview length cap
# ---------------------------------------------------------------------------


def test_preview_at_max_length_is_accepted() -> None:
    text = "a" * PREVIEW_MAX_LENGTH
    event = LogEvent(**_base_kwargs(input_preview=text, output_preview=text))
    assert len(event.input_preview) == PREVIEW_MAX_LENGTH
    assert len(event.output_preview) == PREVIEW_MAX_LENGTH


@pytest.mark.parametrize("field", ["input_preview", "output_preview"])
def test_preview_over_max_length_is_rejected(field: str) -> None:
    too_long = "a" * (PREVIEW_MAX_LENGTH + 1)
    with pytest.raises(ValidationError) as exc:
        LogEvent(**_base_kwargs(**{field: too_long}))
    bad = {err["loc"][0] for err in exc.value.errors()}
    assert field in bad


# ---------------------------------------------------------------------------
# Strictness
# ---------------------------------------------------------------------------


def test_extra_field_is_rejected() -> None:
    """extra='forbid' protects against silent contract drift."""
    with pytest.raises(ValidationError) as exc:
        LogEvent(**_base_kwargs(extra_field="oops"))

    extras = {err["loc"][0] for err in exc.value.errors() if err["type"] == "extra_forbidden"}
    assert "extra_field" in extras


def test_model_is_frozen() -> None:
    event = LogEvent(**_base_kwargs())
    with pytest.raises(ValidationError):
        event.latency_ms = 9999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Type coercion / parsing
# ---------------------------------------------------------------------------


def test_uuid_accepted_as_string() -> None:
    """Pydantic v2 coerces UUID strings — useful when parsing JSON payloads."""
    eid = "11111111-1111-1111-1111-111111111111"
    event = LogEvent(**_base_kwargs(event_id=eid))
    assert event.event_id == UUID(eid)


def test_malformed_uuid_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LogEvent(**_base_kwargs(event_id="not-a-uuid"))


def test_iso_datetime_is_accepted() -> None:
    event = LogEvent(
        **_base_kwargs(
            started_at="2026-01-01T12:00:00+00:00", finished_at="2026-01-01T12:00:01+00:00"
        )
    )
    assert event.started_at == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# JSON round-trip — protects the inter-service wire format
# ---------------------------------------------------------------------------


def test_round_trip_preserves_all_optional_fields() -> None:
    original = LogEvent(
        **_base_kwargs(
            message_id=uuid4(),
            ttft_ms=120,
            prompt_tokens=10,
            completion_tokens=20,
            status="error",
            error_type="ProviderError",
            error_message="503 from upstream",
            http_status=503,
            raw_metadata={"k": "v", "nested": {"a": 1}},
        )
    )

    payload = original.model_dump_json()
    restored = LogEvent.model_validate_json(payload)

    assert restored == original
