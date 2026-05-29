"""IngestionRecord — one event being intook (PRD §5.3).

Pairs the incoming :class:`LogEvent` with an internally-generated
``ingestion_id`` so the worker can correlate Redis-Stream rows with
the original HTTP request when troubleshooting. The LogEvent itself
keeps its ``event_id`` for idempotency at the worker (PRD §6.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from contracts.log_event import LogEvent


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class IngestionRecord:
    ingestion_id: UUID
    event: LogEvent
    received_at: datetime = field(default_factory=_utc_now)

    @classmethod
    def new(cls, *, event: LogEvent, ingestion_id: UUID | None = None) -> IngestionRecord:
        return cls(ingestion_id=ingestion_id or uuid4(), event=event)

    def to_stream_payload(self) -> dict[str, str]:
        """Build the {key: str} payload XADDed to the ``inference_logs`` stream.

        Schema (PRD §7.3):
            ingestion_id   stringified UUID
            event          JSON-serialised LogEvent
        """
        return {
            "ingestion_id": str(self.ingestion_id),
            "event": self.event.model_dump_json(),
        }
