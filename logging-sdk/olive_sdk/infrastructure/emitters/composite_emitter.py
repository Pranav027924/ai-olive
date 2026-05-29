"""CompositeEmitter — fan-out tee to multiple emitters (Phase 4.9).

Used by the chat-service to ship LogEvents over HTTP to the ingestion
service *and* write them to a local JSONL file at the same time —
so dev can ``tail -f logs/inference.jsonl`` while production analytics
still flow through Redis Streams.

A failing branch must not take down the others. ``asyncio.gather``
with ``return_exceptions=True`` lets us collect failures without
re-raising; the caller (typically a Tracker exit path) sees the
``emit`` call succeed regardless.
"""

from __future__ import annotations

import asyncio

from contracts.log_event import LogEvent

from olive_sdk.application.emitter_port import EmitterPort


class CompositeEmitter(EmitterPort):
    def __init__(self, *, emitters: list[EmitterPort]) -> None:
        if not emitters:
            raise ValueError("CompositeEmitter requires at least one emitter")
        self._emitters = list(emitters)

    async def emit(self, event: LogEvent) -> None:
        await asyncio.gather(
            *(e.emit(event) for e in self._emitters),
            return_exceptions=True,
        )
