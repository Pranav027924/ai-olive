"""StreamingResponse — in-flight assistant-message state (PRD §13 Phase 2.1).

Transient stateful value object: it exists only in memory during a
single streaming handler invocation. It is *not* persisted; once the
stream reaches a terminal state the handler maps the final content
and state onto a regular :class:`Message` via
``Session.add_assistant_message``.

State machine:

    ACTIVE ──complete()──▶ COMPLETED   (terminal)
       │
       ├──cancel()──────▶ CANCELLED   (terminal, partial content kept)
       │
       └──error()───────▶ ERRORED     (terminal, partial content kept)

Calling ``push``, ``complete``, ``cancel``, or ``error`` once the
state is terminal raises :class:`InvalidStreamState`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from chat_service.domain.errors import InvalidStreamState


class StreamingState(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERRORED = "errored"


@dataclass(slots=True)
class StreamingResponse:
    session_id: UUID
    message_id: UUID
    state: StreamingState = StreamingState.ACTIVE
    chunks: list[str] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.state is not StreamingState.ACTIVE

    @property
    def content(self) -> str:
        return "".join(self.chunks)

    def push(self, chunk: str) -> None:
        self._guard_active("push to")
        self.chunks.append(chunk)

    def complete(self) -> None:
        self._guard_active("complete")
        self.state = StreamingState.COMPLETED

    def cancel(self) -> None:
        self._guard_active("cancel")
        self.state = StreamingState.CANCELLED

    def error(self) -> None:
        self._guard_active("error")
        self.state = StreamingState.ERRORED

    def _guard_active(self, verb: str) -> None:
        if self.is_terminal:
            raise InvalidStreamState(verb, self.state)
