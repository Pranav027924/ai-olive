"""CancellationStore — outbound port for per-session cancel flags.

A user pressing the cancel button on the UI hits ``POST
/chat/{id}/cancel``, which routes to ``CancelStreamHandler``
(Phase 2.5). The handler ``mark_cancelled``s the session id; the
in-flight ``StreamAssistantResponseHandler`` polls ``is_cancelled``
between LLM tokens and stops with state=CANCELLED.

Phase 2.6 lands the production :class:`RedisCancellationStore`.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class CancellationStore(Protocol):
    """Async flag store keyed by session id."""

    async def mark_cancelled(self, session_id: UUID) -> None:
        """Set the cancel flag. Should be idempotent."""

    async def is_cancelled(self, session_id: UUID) -> bool:
        """Return ``True`` iff a cancel flag is currently set."""

    async def clear(self, session_id: UUID) -> None:
        """Remove the flag. Should be idempotent."""
