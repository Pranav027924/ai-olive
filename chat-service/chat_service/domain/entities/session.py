"""Session — aggregate root for the chat service domain.

Owns its ``messages`` list and is the only entry point for mutating
them (PRD §5.3, §10.1). All time inputs are injectable so domain
tests don't depend on the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ..errors import InvalidStatusTransition, SessionAlreadyTerminal
from ..value_objects.message_role import MessageRole
from ..value_objects.message_status import MessageStatus
from ..value_objects.model_config import ModelConfig
from ..value_objects.session_status import SessionStatus
from .message import Message

# Allowed transitions out of each status. Terminal statuses
# (ARCHIVED, DELETED) have no outgoing transitions.
_ALLOWED_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.ACTIVE: frozenset(
        {
            SessionStatus.CANCELLED,
            SessionStatus.COMPLETED,
            SessionStatus.ARCHIVED,
            SessionStatus.DELETED,
        }
    ),
    SessionStatus.CANCELLED: frozenset({SessionStatus.ARCHIVED, SessionStatus.DELETED}),
    SessionStatus.COMPLETED: frozenset({SessionStatus.ARCHIVED, SessionStatus.DELETED}),
    SessionStatus.ARCHIVED: frozenset({SessionStatus.DELETED}),
    SessionStatus.DELETED: frozenset(),
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Session:
    id: UUID
    user_id: UUID
    title: str | None
    system_prompt: str | None
    config: ModelConfig
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    messages: list[Message] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        config: ModelConfig,
        title: str | None = None,
        system_prompt: str | None = None,
        session_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Session:
        ts = now or _utc_now()
        return cls(
            id=session_id or uuid4(),
            user_id=user_id,
            title=title,
            system_prompt=system_prompt,
            config=config,
            status=SessionStatus.ACTIVE,
            created_at=ts,
            updated_at=ts,
            messages=[],
        )

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def add_user_message(
        self,
        content: str,
        *,
        message_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Message:
        """Append a user-authored message. Always lands as COMPLETE in Phase 1."""
        return self._append_message(
            role=MessageRole.USER,
            content=content,
            status=MessageStatus.COMPLETE,
            message_id=message_id,
            now=now,
        )

    def add_assistant_message(
        self,
        content: str,
        *,
        status: MessageStatus = MessageStatus.COMPLETE,
        message_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Message:
        """Append an assistant-authored message. Status is COMPLETE in Phase 1;
        Phase 2 will start in PENDING during streaming."""
        return self._append_message(
            role=MessageRole.ASSISTANT,
            content=content,
            status=status,
            message_id=message_id,
            now=now,
        )

    def transition_to(self, target: SessionStatus, *, now: datetime | None = None) -> None:
        """Move the session to ``target``. Raises on illegal transitions."""
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidStatusTransition(self.status, target)
        self.status = target
        self.updated_at = now or _utc_now()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _append_message(
        self,
        *,
        role: MessageRole,
        content: str,
        status: MessageStatus,
        message_id: UUID | None,
        now: datetime | None,
    ) -> Message:
        if self.status.is_terminal:
            raise SessionAlreadyTerminal(self.status)
        ts = now or _utc_now()
        msg = Message(
            id=message_id or uuid4(),
            role=role,
            content=content,
            seq=len(self.messages) + 1,
            status=status,
            created_at=ts,
        )
        self.messages.append(msg)
        self.updated_at = ts
        return msg
