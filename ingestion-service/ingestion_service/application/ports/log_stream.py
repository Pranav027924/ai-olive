"""LogStream — outbound port for the Redis-Streams hop (PRD §6.3).

Phase 4.4 ships :class:`RedisStreamAdapter`. Tests use an in-memory
implementation that records the payloads.
"""

from __future__ import annotations

from typing import Protocol


class LogStream(Protocol):
    async def add(self, payload: dict[str, str]) -> str:
        """XADD ``payload`` and return the Redis-Streams message id (e.g. ``"…-0"``)."""
