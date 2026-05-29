"""LogRepository — outbound port for the Postgres write side (PRD §6.4)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from worker_service.domain.entities.processed_log import ProcessedLog


class LogRepository(Protocol):
    async def exists(self, event_id: UUID) -> bool:
        """Return True iff an inference_logs row with this id is already present."""

    async def insert(self, processed: ProcessedLog) -> None:
        """Persist one ProcessedLog. Writes ``logs.inference_logs`` and, when
        ``processed.has_error`` is True, an accompanying ``logs.log_errors``
        row inside a single transaction."""
