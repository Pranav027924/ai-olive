"""UploadAttachment — store blob + create pending row (PRD §6.8).

Handles the synchronous portion of an upload: write bytes to
ObjectStorage under a deterministic key, create an Attachment row
with ``parse_status='pending'``, and return it. The caller (HTTP
router) is responsible for scheduling the asynchronous
ProcessAttachment task afterwards.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from media_service.application.ports.object_storage import ObjectStorage

from chat_service.application.ports.attachment_repository import AttachmentRepository
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.errors import SessionNotFound
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.parse_status import ParseStatus


@dataclass(frozen=True, slots=True)
class UploadAttachmentCommand:
    session_id: UUID
    filename: str
    mime_type: str
    data: bytes
    kind: AttachmentKind


@dataclass(frozen=True, slots=True)
class UploadAttachmentResult:
    attachment: Attachment


class UploadAttachmentHandler:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        attachments: AttachmentRepository,
        storage: ObjectStorage,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._sessions = sessions
        self._attachments = attachments
        self._storage = storage
        self._clock = clock
        self._id_factory = id_factory

    async def handle(self, cmd: UploadAttachmentCommand) -> UploadAttachmentResult:
        session = await self._sessions.get(cmd.session_id)
        if session is None:
            raise SessionNotFound(cmd.session_id)

        attachment_id = self._id_factory()
        s3_key = f"sessions/{cmd.session_id}/attachments/{attachment_id}/{cmd.filename}"
        await self._storage.put(key=s3_key, data=cmd.data, content_type=cmd.mime_type)

        attachment = Attachment(
            id=attachment_id,
            session_id=cmd.session_id,
            kind=cmd.kind,
            filename=cmd.filename,
            mime_type=cmd.mime_type,
            size_bytes=len(cmd.data),
            s3_key=s3_key,
            parse_status=ParseStatus.PENDING,
            created_at=self._clock(),
        )
        await self._attachments.save(attachment)
        return UploadAttachmentResult(attachment=attachment)
