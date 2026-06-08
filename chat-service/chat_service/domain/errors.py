"""Domain-level exceptions for the chat service.

Raised by entities and domain services. Caught by the application
layer and translated to HTTP problem details at the interfaces layer
(PRD §9.6).
"""

from __future__ import annotations

from .value_objects.session_status import SessionStatus


class ChatDomainError(Exception):
    """Base class for all chat-service domain errors."""


class SessionNotFound(ChatDomainError):
    """Raised when a session lookup fails."""


class SessionAlreadyTerminal(ChatDomainError):
    """Attempted to mutate a session whose status is terminal (archived/deleted)."""

    def __init__(self, status: SessionStatus) -> None:
        super().__init__(f"Session is {status.value}; no further modifications allowed.")
        self.status = status


class InvalidStatusTransition(ChatDomainError):
    """Attempted an illegal session-status transition."""

    def __init__(self, frm: SessionStatus, to: SessionStatus) -> None:
        super().__init__(f"Cannot transition session from {frm.value} to {to.value}.")
        self.frm = frm
        self.to = to


class InvalidStreamState(ChatDomainError):
    """Attempted to mutate a StreamingResponse that is already terminal."""

    def __init__(self, verb: str, state: object) -> None:
        super().__init__(f"Cannot {verb} a stream in state '{state}'.")
        self.verb = verb
        self.state = state


class InvalidAttachmentState(ChatDomainError):
    """Attempted to transition an Attachment from a non-pending state."""
