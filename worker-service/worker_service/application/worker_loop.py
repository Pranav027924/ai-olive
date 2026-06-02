"""WorkerLoop — the long-running drain loop (Phase 5.10).

Single async loop that reads a batch from the StreamConsumer,
processes each event via ProcessLogEventHandler, and ACKs the
messages it successfully handled. ``shutdown()`` flips an Event so
the next loop iteration exits — used by the CLI's SIGTERM/SIGINT
handlers.

Failure semantics:
- A pydantic ``ValidationError`` on the inbound event payload is
  considered a poison message: we ACK it so it doesn't loop forever.
  Dead-letter handling lands in Phase 9.6.
- Any other exception during ``handle`` is treated as transient: the
  message is left un-acked so Redis Streams redelivers it after the
  group's pending timeout.
"""

from __future__ import annotations

import asyncio

from contracts.log_event import LogEvent
from pydantic import ValidationError

from worker_service.application.ports.stream_consumer import StreamConsumer, StreamMessage
from worker_service.application.use_cases.process_log_event import (
    ProcessLogEventCommand,
    ProcessLogEventHandler,
)

DEFAULT_BATCH_SIZE = 10
DEFAULT_POLL_BLOCK_MS = 5000


class WorkerLoop:
    def __init__(
        self,
        *,
        consumer: StreamConsumer,
        handler: ProcessLogEventHandler,
        batch_size: int = DEFAULT_BATCH_SIZE,
        poll_block_ms: int = DEFAULT_POLL_BLOCK_MS,
    ) -> None:
        self._consumer = consumer
        self._handler = handler
        self._batch_size = batch_size
        self._poll_block_ms = poll_block_ms
        self._shutdown = asyncio.Event()

    @property
    def shutdown_event(self) -> asyncio.Event:
        return self._shutdown

    def shutdown(self) -> None:
        self._shutdown.set()

    async def run_once(self) -> int:
        """Drain one batch. Returns the number of events successfully
        processed (and ACKed)."""
        # Cheap explicit yield so the event loop can deliver SIGTERM /
        # SIGINT (or test-time shutdown signals) even when the consumer
        # returns synchronously without hitting any real I/O.
        await asyncio.sleep(0)
        messages = await self._consumer.read(
            max_messages=self._batch_size,
            block_ms=self._poll_block_ms,
        )
        ack_ids: list[str] = []
        for message in messages:
            if await self._process(message):
                ack_ids.append(message.message_id)
        await self._consumer.ack(ack_ids)
        return len(ack_ids)

    async def run_forever(self) -> None:
        while not self._shutdown.is_set():
            await self.run_once()

    async def _process(self, message: StreamMessage) -> bool:
        raw = message.payload.get("event", "")
        try:
            event = LogEvent.model_validate_json(raw)
        except ValidationError:
            # Poison: ack so it doesn't redeliver forever. DLQ in Phase 9.6.
            return True
        try:
            await self._handler.handle(ProcessLogEventCommand(event=event))
        except Exception:
            # Transient failure: don't ack so Redis redelivers.
            return False
        return True
