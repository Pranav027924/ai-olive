"""ProcessAttachment — async parse/transcribe step (PRD §6.8, §6.9).

Runs after :class:`UploadAttachmentHandler` has persisted the row.
Pulls the bytes back out of storage, routes them to the right
extractor (parser for documents, transcriber for audio), and
updates the attachment with the extracted text + a terminal
``parse_status``. Any exception transitions the row to ``failed``
so the chat-service never serves a half-written attachment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from media_service.application.ports.object_storage import ObjectStorage
from media_service.application.use_cases.parse_document import (
    ParseDocumentCommand,
    ParseDocumentHandler,
)
from media_service.application.use_cases.transcribe_audio import (
    TranscribeAudioCommand,
    TranscribeAudioHandler,
)
from media_service.domain.entities.audio import Audio
from media_service.domain.entities.document import Document

from chat_service.application.ports.attachment_repository import AttachmentRepository
from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.value_objects.attachment_kind import AttachmentKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProcessAttachmentCommand:
    attachment_id: UUID


class ProcessAttachmentHandler:
    def __init__(
        self,
        *,
        attachments: AttachmentRepository,
        storage: ObjectStorage,
        parser: ParseDocumentHandler,
        transcriber: TranscribeAudioHandler,
    ) -> None:
        self._attachments = attachments
        self._storage = storage
        self._parser = parser
        self._transcriber = transcriber

    async def handle(self, cmd: ProcessAttachmentCommand) -> Attachment:
        attachment = await self._attachments.get(cmd.attachment_id)
        if attachment is None:
            raise LookupError(f"attachment {cmd.attachment_id} not found")

        try:
            data = await self._storage.get(key=attachment.s3_key)
            updated = await self._extract(attachment, data)
        except Exception:
            logger.exception("attachment %s failed to process", attachment.id)
            updated = attachment.mark_failed()

        await self._attachments.save(updated)
        return updated

    async def _extract(self, attachment: Attachment, data: bytes) -> Attachment:
        if attachment.kind is AttachmentKind.AUDIO:
            audio_result = await self._transcriber.handle(
                TranscribeAudioCommand(
                    audio=Audio(
                        filename=attachment.filename,
                        mime_type=attachment.mime_type,
                        size_bytes=attachment.size_bytes,
                    ),
                    data=data,
                )
            )
            return attachment.mark_complete(parsed_text=None, transcript=audio_result.content.text)

        doc_result = await self._parser.handle(
            ParseDocumentCommand(
                document=Document(
                    filename=attachment.filename,
                    mime_type=attachment.mime_type,
                    size_bytes=attachment.size_bytes,
                ),
                data=data,
            )
        )
        return attachment.mark_complete(parsed_text=doc_result.content.text, transcript=None)
