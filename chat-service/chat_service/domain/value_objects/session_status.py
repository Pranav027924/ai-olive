"""SessionStatus — lifecycle states for a chat session.

Matches the CHECK constraint on ``chat.sessions.status`` (PRD §8.1).
Status transitions are enforced by :class:`Session`, not by the enum.
"""

from __future__ import annotations

from enum import StrEnum


class SessionStatus(StrEnum):
    """Terminal and non-terminal lifecycle states for a chat session."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    DELETED = "deleted"

    @property
    def is_terminal(self) -> bool:
        """A terminal status disallows adding new messages."""
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES: frozenset[SessionStatus] = frozenset(
    {
        SessionStatus.ARCHIVED,
        SessionStatus.DELETED,
    }
)
