"""Smoke test for Tracker (Phase 3.6).

Locks in: the success path produces a LogEvent with the expected
ids, status, tokens, previews, and TTFT. Detailed coverage
(error / cancel / timeout) lands in Phase 3.7.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from contracts.log_event import LogEvent
from olive_sdk.application.tracker import Tracker


class _CapturingEmitter:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    async def emit(self, event: LogEvent) -> None:
        self.events.append(event)


async def test_success_path_emits_log_event() -> None:
    emitter = _CapturingEmitter()
    session_id = uuid4()
    message_id = uuid4()

    tracker = Tracker(
        emitter=emitter,
        session_id=session_id,
        message_id=message_id,
        provider="anthropic",
        model="claude-opus-4-7",
        sdk_version="0.1.0",
        input_preview="hi",
    )
    async with tracker:
        await asyncio.sleep(0)
        tracker.record_chunk("hello ")
        tracker.record_chunk("world")
        tracker.record_usage(prompt_tokens=10, completion_tokens=20)

    assert len(emitter.events) == 1
    ev = emitter.events[0]

    assert isinstance(ev, LogEvent)
    assert isinstance(ev.event_id, UUID)
    assert ev.session_id == session_id
    assert ev.message_id == message_id
    assert ev.provider == "anthropic"
    assert ev.model == "claude-opus-4-7"
    assert ev.status == "success"
    assert ev.prompt_tokens == 10
    assert ev.completion_tokens == 20
    assert ev.input_preview == "hi"
    assert ev.output_preview == "hello world"
    assert ev.ttft_ms is not None
    assert ev.latency_ms >= 0
    assert ev.error_type is None
    assert ev.error_message is None
