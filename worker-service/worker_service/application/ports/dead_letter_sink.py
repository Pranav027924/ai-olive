"""DeadLetterSink — outbound port for poison messages (PRD §9.6).

A message whose payload can't be parsed into a :class:`LogEvent`
(a "poison" message) would otherwise be ACKed and lost. The worker
instead hands it to a DeadLetterSink so it lands in a separate
dead-letter stream where it can be inspected and replayed.
"""

from __future__ import annotations

from typing import Protocol

from worker_service.application.ports.stream_consumer import StreamMessage


class DeadLetterSink(Protocol):
    async def send(self, message: StreamMessage, *, reason: str) -> None:
        """Persist ``message`` to the dead-letter stream with ``reason``."""
