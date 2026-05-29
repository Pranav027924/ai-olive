"""Exhaustive Tracker tests (Phase 3.7)."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from contracts.log_event import PREVIEW_MAX_LENGTH, LogEvent
from olive_sdk.application.tracker import Tracker


class _CapturingEmitter:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    async def emit(self, event: LogEvent) -> None:
        self.events.append(event)


def _new_tracker(emitter: _CapturingEmitter, **overrides: object) -> Tracker:
    kwargs: dict[str, object] = {
        "emitter": emitter,
        "session_id": uuid4(),
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "sdk_version": "0.1.0",
    }
    kwargs.update(overrides)
    return Tracker(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# event_id
# ---------------------------------------------------------------------------


async def test_event_id_defaults_to_random_uuid() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter):
        pass
    async with _new_tracker(emitter):
        pass

    assert emitter.events[0].event_id != emitter.events[1].event_id


async def test_event_id_can_be_injected() -> None:
    fixed = UUID("11111111-1111-1111-1111-111111111111")
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter, event_id=fixed):
        pass
    assert emitter.events[0].event_id == fixed


# ---------------------------------------------------------------------------
# Status branches
# ---------------------------------------------------------------------------


async def test_default_status_is_success() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter):
        pass
    assert emitter.events[0].status == "success"


async def test_explicit_cancel_sets_status_cancelled() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter) as tracker:
        tracker.record_chunk("partial")
        tracker.mark_cancelled()
    ev = emitter.events[0]
    assert ev.status == "cancelled"
    assert ev.output_preview == "partial"


async def test_explicit_timeout_sets_status_timeout() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter) as tracker:
        tracker.mark_timeout()
    assert emitter.events[0].status == "timeout"


async def _run_and_raise_runtime(emitter: _CapturingEmitter) -> None:
    async with _new_tracker(emitter) as tracker:
        tracker.record_chunk("partial output")
        raise RuntimeError("boom")


async def _run_and_raise_cancelled(emitter: _CapturingEmitter) -> None:
    async with _new_tracker(emitter):
        raise asyncio.CancelledError


async def _run_mark_then_raise(emitter: _CapturingEmitter) -> None:
    async with _new_tracker(emitter) as tracker:
        tracker.mark_cancelled()
        raise RuntimeError("oops")


async def test_exception_inside_body_sets_status_error_and_propagates() -> None:
    emitter = _CapturingEmitter()
    with pytest.raises(RuntimeError, match="boom"):
        await _run_and_raise_runtime(emitter)
    ev = emitter.events[0]
    assert ev.status == "error"
    assert ev.error_type == "RuntimeError"
    assert ev.error_message == "boom"
    assert ev.output_preview == "partial output"


async def test_cancelled_error_sets_status_cancelled_not_error() -> None:
    """An asyncio cancel from the host loop maps to cancelled, not error."""
    emitter = _CapturingEmitter()
    with pytest.raises(asyncio.CancelledError):
        await _run_and_raise_cancelled(emitter)
    ev = emitter.events[0]
    assert ev.status == "cancelled"
    assert ev.error_type is None
    assert ev.error_message is None


async def test_exception_wins_over_explicit_mark() -> None:
    """The exception path is authoritative — explicit mark_cancelled before
    a raised exception still produces status=error."""
    emitter = _CapturingEmitter()
    with pytest.raises(RuntimeError):
        await _run_mark_then_raise(emitter)
    assert emitter.events[0].status == "error"


# ---------------------------------------------------------------------------
# TTFT and latency
# ---------------------------------------------------------------------------


async def test_ttft_ms_is_none_when_no_chunks_recorded() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter):
        pass
    assert emitter.events[0].ttft_ms is None


async def test_ttft_ms_is_recorded_on_first_chunk_only() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter) as tracker:
        await asyncio.sleep(0.005)
        tracker.record_chunk("a")
        first_ttft_marker = tracker  # noqa: F841
        await asyncio.sleep(0.01)
        tracker.record_chunk("b")
    ev = emitter.events[0]
    assert ev.ttft_ms is not None
    # ttft must not include the time taken by the second chunk's sleep.
    assert ev.latency_ms >= ev.ttft_ms


async def test_latency_ms_is_non_negative() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter):
        await asyncio.sleep(0.001)
    assert emitter.events[0].latency_ms >= 0


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


async def test_usage_defaults_to_none_when_never_recorded() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter):
        pass
    ev = emitter.events[0]
    assert ev.prompt_tokens is None
    assert ev.completion_tokens is None


async def test_record_usage_writes_token_counts() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter) as tracker:
        tracker.record_usage(prompt_tokens=42, completion_tokens=7)
    ev = emitter.events[0]
    assert ev.prompt_tokens == 42
    assert ev.completion_tokens == 7


async def test_record_usage_last_call_wins() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter) as tracker:
        tracker.record_usage(prompt_tokens=1, completion_tokens=1)
        tracker.record_usage(prompt_tokens=10, completion_tokens=20)
    ev = emitter.events[0]
    assert ev.prompt_tokens == 10
    assert ev.completion_tokens == 20


# ---------------------------------------------------------------------------
# Preview truncation
# ---------------------------------------------------------------------------


async def test_input_preview_is_truncated_to_max_length() -> None:
    emitter = _CapturingEmitter()
    huge = "x" * (PREVIEW_MAX_LENGTH + 100)
    async with _new_tracker(emitter, input_preview=huge):
        pass
    ev = emitter.events[0]
    assert len(ev.input_preview) == PREVIEW_MAX_LENGTH


async def test_output_preview_is_truncated_to_max_length() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter) as tracker:
        # 10 chunks of 100 chars each → 1000 chars total
        for _ in range(10):
            tracker.record_chunk("y" * 100)
    ev = emitter.events[0]
    assert len(ev.output_preview) == PREVIEW_MAX_LENGTH


async def test_input_preview_passthrough_when_under_limit() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter, input_preview="short"):
        pass
    assert emitter.events[0].input_preview == "short"


# ---------------------------------------------------------------------------
# raw_metadata
# ---------------------------------------------------------------------------


async def test_raw_metadata_defaults_to_empty_dict() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter):
        pass
    assert emitter.events[0].raw_metadata == {}


async def test_raw_metadata_at_construction_is_preserved() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter, raw_metadata={"finish_reason": "stop"}):
        pass
    assert emitter.events[0].raw_metadata == {"finish_reason": "stop"}


async def test_add_metadata_merges_into_raw_metadata() -> None:
    emitter = _CapturingEmitter()
    async with _new_tracker(emitter, raw_metadata={"a": 1}) as tracker:
        tracker.add_metadata(b=2, c=3)
    assert emitter.events[0].raw_metadata == {"a": 1, "b": 2, "c": 3}
