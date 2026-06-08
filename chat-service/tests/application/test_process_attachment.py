"""Tests for ProcessAttachmentHandler (Phase 6.8)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from chat_service.application.use_cases.process_attachment import (
    ProcessAttachmentCommand,
    ProcessAttachmentHandler,
)
from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.parse_status import ParseStatus
from media_service.application.use_cases.parse_document import (
    ParseDocumentHandler,
    ParserRegistry,
)
from media_service.application.use_cases.transcribe_audio import TranscribeAudioHandler
from media_service.domain.entities.audio import Audio
from media_service.domain.entities.document import Document
from media_service.domain.services.document_parser import DocumentParser
from media_service.domain.services.transcriber import Transcriber
from media_service.domain.value_objects.extracted_content import ExtractedContent
from media_service.infrastructure.storage.in_memory_object_storage import (
    InMemoryObjectStorage,
)

from tests.conftest import InMemoryAttachmentRepository


class _ScriptedParser(DocumentParser):
    def __init__(self, *, mime: str, text: str = "parsed text") -> None:
        self._mime = mime
        self._text = text

    @property
    def mime_types(self) -> tuple[str, ...]:
        return (self._mime,)

    async def parse(self, *, document: Document, data: bytes) -> ExtractedContent:
        return ExtractedContent(text=self._text, metadata={"page_count": 1})


class _ScriptedTranscriber(Transcriber):
    def __init__(self, *, text: str = "spoken text") -> None:
        self._text = text

    async def transcribe(self, *, audio: Audio, data: bytes) -> ExtractedContent:
        return ExtractedContent(text=self._text, metadata={"duration_seconds": 1.0})


class _BoomTranscriber(Transcriber):
    async def transcribe(self, *, audio: Audio, data: bytes) -> ExtractedContent:
        raise RuntimeError("model exploded")


def _pending(
    *,
    attachment_id: UUID,
    session_id: UUID,
    kind: AttachmentKind,
    filename: str,
    mime: str,
    s3_key: str,
) -> Attachment:
    return Attachment(
        id=attachment_id,
        session_id=session_id,
        kind=kind,
        filename=filename,
        mime_type=mime,
        size_bytes=8,
        s3_key=s3_key,
        parse_status=ParseStatus.PENDING,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
    )


async def _seed(
    attachments: InMemoryAttachmentRepository,
    storage: InMemoryObjectStorage,
    *,
    attachment: Attachment,
    data: bytes,
) -> None:
    await storage.put(key=attachment.s3_key, data=data, content_type=attachment.mime_type)
    await attachments.save(attachment)


async def test_unknown_attachment_raises_lookup_error(
    attachments: InMemoryAttachmentRepository,
) -> None:
    handler = ProcessAttachmentHandler(
        attachments=attachments,
        storage=InMemoryObjectStorage(),
        parser=ParseDocumentHandler(
            registry=ParserRegistry([_ScriptedParser(mime="application/pdf")])
        ),
        transcriber=TranscribeAudioHandler(transcriber=_ScriptedTranscriber()),
    )

    with pytest.raises(LookupError):
        await handler.handle(ProcessAttachmentCommand(attachment_id=uuid4()))


async def test_file_attachment_runs_parser_and_marks_complete(
    attachments: InMemoryAttachmentRepository,
) -> None:
    storage = InMemoryObjectStorage()
    attachment = _pending(
        attachment_id=uuid4(),
        session_id=uuid4(),
        kind=AttachmentKind.FILE,
        filename="r.pdf",
        mime="application/pdf",
        s3_key="sessions/x/attachments/y/r.pdf",
    )
    await _seed(attachments, storage, attachment=attachment, data=b"%PDFblob")
    handler = ProcessAttachmentHandler(
        attachments=attachments,
        storage=storage,
        parser=ParseDocumentHandler(
            registry=ParserRegistry([_ScriptedParser(mime="application/pdf", text="hello")])
        ),
        transcriber=TranscribeAudioHandler(transcriber=_ScriptedTranscriber()),
    )

    result = await handler.handle(ProcessAttachmentCommand(attachment_id=attachment.id))

    assert result.parse_status is ParseStatus.COMPLETE
    assert result.parsed_text == "hello"
    assert result.transcript is None

    persisted = await attachments.get(attachment.id)
    assert persisted is not None
    assert persisted.parsed_text == "hello"


async def test_audio_attachment_runs_transcriber_and_marks_complete(
    attachments: InMemoryAttachmentRepository,
) -> None:
    storage = InMemoryObjectStorage()
    attachment = _pending(
        attachment_id=uuid4(),
        session_id=uuid4(),
        kind=AttachmentKind.AUDIO,
        filename="c.wav",
        mime="audio/wav",
        s3_key="sessions/x/attachments/y/c.wav",
    )
    await _seed(attachments, storage, attachment=attachment, data=b"RIFFblob")
    handler = ProcessAttachmentHandler(
        attachments=attachments,
        storage=storage,
        parser=ParseDocumentHandler(
            registry=ParserRegistry([_ScriptedParser(mime="application/pdf")])
        ),
        transcriber=TranscribeAudioHandler(transcriber=_ScriptedTranscriber(text="hey there")),
    )

    result = await handler.handle(ProcessAttachmentCommand(attachment_id=attachment.id))

    assert result.parse_status is ParseStatus.COMPLETE
    assert result.transcript == "hey there"
    assert result.parsed_text is None


async def test_transcriber_exception_marks_attachment_failed(
    attachments: InMemoryAttachmentRepository,
) -> None:
    storage = InMemoryObjectStorage()
    attachment = _pending(
        attachment_id=uuid4(),
        session_id=uuid4(),
        kind=AttachmentKind.AUDIO,
        filename="c.wav",
        mime="audio/wav",
        s3_key="sessions/x/attachments/y/c.wav",
    )
    await _seed(attachments, storage, attachment=attachment, data=b"RIFFblob")
    handler = ProcessAttachmentHandler(
        attachments=attachments,
        storage=storage,
        parser=ParseDocumentHandler(
            registry=ParserRegistry([_ScriptedParser(mime="application/pdf")])
        ),
        transcriber=TranscribeAudioHandler(transcriber=_BoomTranscriber()),
    )

    result = await handler.handle(ProcessAttachmentCommand(attachment_id=attachment.id))

    assert result.parse_status is ParseStatus.FAILED
    assert result.parsed_text is None
    assert result.transcript is None


async def test_unsupported_file_mime_marks_attachment_failed(
    attachments: InMemoryAttachmentRepository,
) -> None:
    storage = InMemoryObjectStorage()
    attachment = _pending(
        attachment_id=uuid4(),
        session_id=uuid4(),
        kind=AttachmentKind.FILE,
        filename="r.xyz",
        mime="application/x-unknown",
        s3_key="sessions/x/attachments/y/r.xyz",
    )
    await _seed(attachments, storage, attachment=attachment, data=b"x")
    handler = ProcessAttachmentHandler(
        attachments=attachments,
        storage=storage,
        parser=ParseDocumentHandler(
            registry=ParserRegistry([_ScriptedParser(mime="application/pdf")])
        ),
        transcriber=TranscribeAudioHandler(transcriber=_ScriptedTranscriber()),
    )

    result = await handler.handle(ProcessAttachmentCommand(attachment_id=attachment.id))

    assert result.parse_status is ParseStatus.FAILED
