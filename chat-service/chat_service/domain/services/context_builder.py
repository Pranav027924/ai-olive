"""ContextBuilder — rolling context window for the LLM call.

Selects which prior :class:`Message` objects to include when calling
the LLM (PRD §2.1) and composes the system prompt with the text of
any complete attachments (PRD §6.9). Attachments live as side data
on the session — embedding them in the system prompt lets the LLM
reference them without polluting the message history that the UI
renders.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.entities.message import Message
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.parse_status import ParseStatus

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

    def compose_system_prompt(
        self,
        base: str | None,
        attachments: Iterable[Attachment],
    ) -> str | None:
        usable = [a for a in attachments if a.parse_status is ParseStatus.COMPLETE and _text_of(a)]
        if not usable:
            return base

        sections = [f"Attachment {a.filename} ({a.kind.value}):\n{_text_of(a)}" for a in usable]
        attachments_block = "\n\n".join(sections)
        header = "The user has shared the following attachments. Reference them as needed."
        if base:
            return f"{base}\n\n{header}\n\n{attachments_block}"
        return f"{header}\n\n{attachments_block}"


def _text_of(attachment: Attachment) -> str | None:
    if attachment.kind is AttachmentKind.AUDIO:
        return attachment.transcript
    return attachment.parsed_text
