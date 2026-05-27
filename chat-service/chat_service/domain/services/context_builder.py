"""ContextBuilder — rolling context window for the LLM call.

Selects which prior :class:`Message` objects to include when calling
the LLM. PRD §2.1: "rolling context window (last 20 messages by
default, configurable)".
"""

from __future__ import annotations

from dataclasses import dataclass

from chat_service.domain.entities.message import Message
from chat_service.domain.entities.session import Session

DEFAULT_WINDOW = 20


@dataclass(slots=True, frozen=True)
class ContextBuilder:
    """Pure domain service. No I/O.

    Returns the last ``window`` messages from the session in seq order.
    Future revisions may apply token-budget trimming or summarisation.
    """

    window: int = DEFAULT_WINDOW

    def build(self, session: Session) -> list[Message]:
        if self.window <= 0:
            return []
        return list(session.messages[-self.window :])
