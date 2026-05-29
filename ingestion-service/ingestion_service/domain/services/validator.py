"""BatchValidator — guards batch-level invariants (PRD §6.3).

LogEvent itself is fully Pydantic-validated (``extra="forbid"``,
length caps, literal sets) so this layer focuses on rules that
require seeing the whole batch:

- empty batch is rejected (400) so callers don't accidentally
  ack a no-op request.
- batches above MAX_BATCH_SIZE are rejected (413/400) to bound
  the request size and the resulting Redis XADD burst.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.log_event import LogEvent

from ingestion_service.domain.errors import BatchTooLarge, EmptyBatch


@dataclass(frozen=True, slots=True)
class BatchValidator:
    MAX_BATCH_SIZE: int = 500

    def validate(self, events: list[LogEvent]) -> None:
        if not events:
            raise EmptyBatch
        if len(events) > self.MAX_BATCH_SIZE:
            raise BatchTooLarge(size=len(events), limit=self.MAX_BATCH_SIZE)
