"""CircuitBreaker — fallback emitter when the primary keeps failing (Phase 4.9).

State machine::

    CLOSED ──(N consecutive raises from primary.emit)──▶ OPEN
       ▲                                                  │
       │                                                  │ probe_interval elapses
       │                                                  ▼
       │                                              HALF_OPEN ──(success)──▶ CLOSED
       │                                                  │
       └──────────────(failure)───────────────────────────┘

While OPEN every event goes straight to the fallback emitter so the
caller never sees a delay from the failing primary. The probe at
HALF_OPEN sends one event through the primary; on success the
breaker closes, on failure it re-opens.

This component requires the primary emitter to *raise* on failure —
it has no other way of knowing. HttpEmitter is fire-and-forget and
swallows failures; pair it with FileEmitter through a
:class:`CompositeEmitter` instead, and reserve the breaker for
emitters that surface failures directly (such as a synchronous HTTP
fallback in a future phase).
"""

from __future__ import annotations

import time
from typing import Literal

from contracts.log_event import LogEvent

from olive_sdk.application.emitter_port import EmitterPort

State = Literal["closed", "open", "half-open"]


class CircuitBreaker(EmitterPort):
    def __init__(
        self,
        *,
        primary: EmitterPort,
        fallback: EmitterPort,
        failure_threshold: int = 5,
        probe_interval_seconds: float = 30.0,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if probe_interval_seconds < 0:
            raise ValueError("probe_interval_seconds must be >= 0")
        self._primary = primary
        self._fallback = fallback
        self._failure_threshold = failure_threshold
        self._probe_interval = probe_interval_seconds

        self._state: State = "closed"
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> State:
        return self._state

    async def emit(self, event: LogEvent) -> None:
        if self._state == "open" and self._should_probe():
            self._state = "half-open"

        if self._state == "open":
            await self._fallback.emit(event)
            return

        try:
            await self._primary.emit(event)
        except Exception:
            await self._handle_failure(event)
            return

        # Success path: reset counters; close on a successful probe.
        if self._state == "half-open":
            self._state = "closed"
            self._opened_at = None
        self._consecutive_failures = 0

    def _should_probe(self) -> bool:
        if self._opened_at is None:
            return False
        return (time.monotonic() - self._opened_at) >= self._probe_interval

    async def _handle_failure(self, event: LogEvent) -> None:
        if self._state == "half-open":
            # Probe failed; immediately re-open and route to fallback.
            self._state = "open"
            self._opened_at = time.monotonic()
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
        await self._fallback.emit(event)
