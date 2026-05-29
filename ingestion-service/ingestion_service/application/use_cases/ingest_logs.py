"""IngestLogs — command use case for the ingestion hot path (PRD §6.3).

Validates the batch, builds one IngestionRecord per event, XADDs each
record's payload to the LogStream, and returns the parallel lists of
ingestion ids and Redis-Stream message ids so the HTTP layer can
echo them in the 202 response.

There are deliberately no DB writes here (PRD §2.3): everything
beyond the stream hop is the Worker's job (Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from contracts.log_event import LogEvent

from ingestion_service.application.ports.log_stream import LogStream
from ingestion_service.domain.entities.ingestion_record import IngestionRecord
from ingestion_service.domain.services.validator import BatchValidator


@dataclass(frozen=True, slots=True)
class IngestLogsCommand:
    events: list[LogEvent]


@dataclass(frozen=True, slots=True)
class IngestLogsResult:
    ingestion_ids: list[UUID]
    stream_ids: list[str]


class IngestLogsHandler:
    def __init__(
        self,
        *,
        stream: LogStream,
        validator: BatchValidator | None = None,
    ) -> None:
        self._stream = stream
        self._validator = validator or BatchValidator()

    async def handle(self, cmd: IngestLogsCommand) -> IngestLogsResult:
        self._validator.validate(cmd.events)

        records = [IngestionRecord.new(event=ev) for ev in cmd.events]
        stream_ids: list[str] = []
        for record in records:
            sid = await self._stream.add(record.to_stream_payload())
            stream_ids.append(sid)

        return IngestLogsResult(
            ingestion_ids=[r.ingestion_id for r in records],
            stream_ids=stream_ids,
        )
