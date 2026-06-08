"""Attachment — an uploaded blob bound to a chat session (PRD §6.8, §8.1).

Created when the user uploads a file or voice clip; the bytes live in
ObjectStorage under ``s3_key`` and the parsed/transcribed text gets
filled in asynchronously by the background processor.

State machine: ``pending`` is the only non-terminal state. A
successful parse transitions to ``complete`` and populates the
matching text field (``parsed_text`` for documents,
``transcript`` for audio). A parser error transitions to ``failed``
and the text fields remain ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from chat_service.domain.errors import InvalidAttachmentState
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.parse_status import ParseStatus


@dataclass(frozen=True, slots=True)
class Attachment:
    id: UUID
    session_id: UUID
    kind: AttachmentKind
    filename: str
    mime_type: str
    size_bytes: int
    s3_key: str
    parse_status: ParseStatus
    created_at: datetime
    message_id: UUID | None = None
    parsed_text: str | None = None
    transcript: str | None = None

    def mark_complete(self, *, parsed_text: str | None, transcript: str | None) -> Attachment:
        if self.parse_status is not ParseStatus.PENDING:
            raise InvalidAttachmentState(
                f"cannot mark {self.parse_status.value} attachment as complete"
            )
        return replace(
            self,
            parse_status=ParseStatus.COMPLETE,
            parsed_text=parsed_text,
            transcript=transcript,
        )

    def mark_failed(self) -> Attachment:
        if self.parse_status is not ParseStatus.PENDING:
            raise InvalidAttachmentState(
                f"cannot mark {self.parse_status.value} attachment as failed"
            )
        return replace(self, parse_status=ParseStatus.FAILED)
