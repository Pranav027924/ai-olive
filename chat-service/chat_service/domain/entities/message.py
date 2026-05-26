"""Message — entity within the Session aggregate.

Identity is the ``id``. ``seq`` is monotonically increasing within a
session and unique per ``(session_id, seq)`` at the DB level
(PRD §8.1). Status is mutable so streaming responses can transition
``PENDING`` → ``COMPLETE`` / ``CANCELLED`` / ``ERROR`` in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..value_objects.message_role import MessageRole
from ..value_objects.message_status import MessageStatus


@dataclass(slots=True)
class Message:
    id: UUID
    role: MessageRole
    content: str
    seq: int
    status: MessageStatus
    created_at: datetime
