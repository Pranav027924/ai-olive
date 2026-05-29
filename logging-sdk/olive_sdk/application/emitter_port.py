"""EmitterPort — outbound port for shipping LogEvents (PRD §6.2).

Concrete adapters land in:
- Phase 3.8: FileEmitter (JSONL).
- Phase 4.8: HTTPEmitter (batched POST to the ingestion service).
- Phase 4.9: CompositeEmitter (tee to multiple sinks).
"""

from __future__ import annotations

from typing import Protocol

from contracts.log_event import LogEvent


class EmitterPort(Protocol):
    """Async port for shipping a single LogEvent.

    Implementations should never raise to the caller — instead log the
    failure and degrade. The Tracker's contract is "a LogEvent is built
    on every path"; how / whether it lands is the emitter's problem.
    """

    async def emit(self, event: LogEvent) -> None:
        """Ship the event. Should be idempotent and side-effect-free on
        retries (the worker will dedupe by ``event_id``)."""
