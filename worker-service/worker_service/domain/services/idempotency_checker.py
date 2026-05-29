"""IdempotencyChecker — in-memory cache of already-processed event ids.

Postgres' PRIMARY KEY on ``logs.inference_logs(id, started_at)`` is the
canonical idempotency guard (PRD §10.4 "at-least-once + dedupe"). This
cache is a fast path so a burst of re-deliveries during one worker run
doesn't spam the DB.

Tests inject a checker pre-seeded with ids when they want to assert
the use case short-circuits on a known duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(slots=True)
class IdempotencyChecker:
    _seen: set[UUID] = field(default_factory=set)

    def is_known(self, event_id: UUID) -> bool:
        return event_id in self._seen

    def mark(self, event_id: UUID) -> None:
        self._seen.add(event_id)

    def size(self) -> int:
        return len(self._seen)
