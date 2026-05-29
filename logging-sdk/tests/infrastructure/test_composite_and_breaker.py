"""Tests for CompositeEmitter and CircuitBreaker (Phase 4.9)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from contracts.log_event import LogEvent
from olive_sdk.infrastructure.emitters.circuit_breaker import CircuitBreaker
from olive_sdk.infrastructure.emitters.composite_emitter import CompositeEmitter


def _event(**overrides: Any) -> LogEvent:
    base: dict[str, Any] = {
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
    return LogEvent(**base)


class _RecordingEmitter:
    """Records every emitted event."""

    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    async def emit(self, event: LogEvent) -> None:
        self.events.append(event)


class _FailingEmitter:
    """Raises on demand; otherwise records like _RecordingEmitter."""

    def __init__(self, *, fail_first: int = 0) -> None:
        self._fail_first = fail_first
        self.events: list[LogEvent] = []
        self.call_count = 0

    async def emit(self, event: LogEvent) -> None:
        self.call_count += 1
        if self.call_count <= self._fail_first:
            raise RuntimeError("primary down")
        self.events.append(event)


# ---------------------------------------------------------------------------
# CompositeEmitter
# ---------------------------------------------------------------------------


def test_composite_requires_at_least_one_emitter() -> None:
    with pytest.raises(ValueError, match="at least one emitter"):
        CompositeEmitter(emitters=[])


async def test_composite_tees_to_every_emitter() -> None:
    a = _RecordingEmitter()
    b = _RecordingEmitter()
    c = _RecordingEmitter()
    composite = CompositeEmitter(emitters=[a, b, c])

    ev = _event()
    await composite.emit(ev)

    assert a.events == [ev]
    assert b.events == [ev]
    assert c.events == [ev]


async def test_composite_one_failure_does_not_block_the_others() -> None:
    a = _RecordingEmitter()
    failing = _FailingEmitter(fail_first=10)
    c = _RecordingEmitter()
    composite = CompositeEmitter(emitters=[a, failing, c])

    ev = _event()
    # Must not raise.
    await composite.emit(ev)

    assert a.events == [ev]
    assert c.events == [ev]
    assert failing.events == []
    assert failing.call_count == 1


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_breaker_rejects_invalid_thresholds() -> None:
    a = _RecordingEmitter()
    b = _RecordingEmitter()
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(primary=a, fallback=b, failure_threshold=0)
    with pytest.raises(ValueError, match="probe_interval_seconds"):
        CircuitBreaker(primary=a, fallback=b, probe_interval_seconds=-1)


async def test_closed_breaker_passes_events_to_primary_only() -> None:
    primary = _RecordingEmitter()
    fallback = _RecordingEmitter()
    breaker = CircuitBreaker(primary=primary, fallback=fallback)

    ev = _event()
    await breaker.emit(ev)

    assert primary.events == [ev]
    assert fallback.events == []
    assert breaker.state == "closed"


async def test_breaker_routes_to_fallback_on_failure_and_counts_failures() -> None:
    primary = _FailingEmitter(fail_first=2)
    fallback = _RecordingEmitter()
    breaker = CircuitBreaker(primary=primary, fallback=fallback, failure_threshold=5)

    await breaker.emit(_event())
    await breaker.emit(_event())

    assert primary.call_count == 2
    assert primary.events == []
    assert len(fallback.events) == 2
    assert breaker.state == "closed"


async def test_breaker_opens_after_threshold_consecutive_failures() -> None:
    primary = _FailingEmitter(fail_first=100)  # always fails
    fallback = _RecordingEmitter()
    breaker = CircuitBreaker(primary=primary, fallback=fallback, failure_threshold=3)

    for _ in range(3):
        await breaker.emit(_event())
    assert breaker.state == "open"

    # While open: primary is not even called.
    primary_calls_before = primary.call_count
    await breaker.emit(_event())
    assert primary.call_count == primary_calls_before
    assert len(fallback.events) == 4


async def test_breaker_success_resets_failure_counter() -> None:
    """Non-consecutive failures should not trip the breaker."""
    primary = _FailingEmitter(fail_first=2)  # then succeeds forever
    fallback = _RecordingEmitter()
    breaker = CircuitBreaker(primary=primary, fallback=fallback, failure_threshold=3)

    await breaker.emit(_event())  # fail 1
    await breaker.emit(_event())  # fail 2 — would reach threshold at 3
    await breaker.emit(_event())  # success → reset
    await breaker.emit(_event())  # success
    await breaker.emit(_event())  # success

    assert breaker.state == "closed"
    assert len(fallback.events) == 2
    assert len(primary.events) == 3


async def test_breaker_probes_after_interval_and_closes_on_success() -> None:
    """Once the probe interval elapses the next emit goes through the primary;
    success closes the breaker."""
    primary = _FailingEmitter(fail_first=3)  # then succeeds
    fallback = _RecordingEmitter()
    breaker = CircuitBreaker(
        primary=primary,
        fallback=fallback,
        failure_threshold=3,
        probe_interval_seconds=0.05,
    )

    for _ in range(3):
        await breaker.emit(_event())
    assert breaker.state == "open"

    # Wait past the probe interval.
    await asyncio.sleep(0.1)

    # This call should probe the primary, which now succeeds.
    await breaker.emit(_event())
    state_after_probe: str = breaker.state
    assert state_after_probe == "closed"
    assert primary.call_count == 4  # 3 failing + 1 successful probe


async def test_breaker_probe_failure_reopens_immediately() -> None:
    primary = _FailingEmitter(fail_first=100)  # always fails
    fallback = _RecordingEmitter()
    breaker = CircuitBreaker(
        primary=primary,
        fallback=fallback,
        failure_threshold=2,
        probe_interval_seconds=0.05,
    )

    await breaker.emit(_event())
    await breaker.emit(_event())
    assert breaker.state == "open"

    await asyncio.sleep(0.1)
    await breaker.emit(_event())  # probe — also fails
    assert breaker.state == "open"
    # The probe attempt did call the primary once.
    assert primary.call_count == 3
    assert len(fallback.events) == 3
