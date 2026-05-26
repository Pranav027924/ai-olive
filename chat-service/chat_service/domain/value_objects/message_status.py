"""MessageStatus — lifecycle of a single message.

Matches the CHECK constraint on ``chat.messages.status`` (PRD §8.1).

In Phase 1 (blocking responses) messages go straight to ``COMPLETE``.
``PENDING`` is used in Phase 2 when streaming starts before the
assistant text exists.
"""

from __future__ import annotations

from enum import StrEnum


class MessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"
