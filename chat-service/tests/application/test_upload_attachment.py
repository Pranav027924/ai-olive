"""Tests for UploadAttachmentHandler (Phase 6.8)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from chat_service.application.use_cases.create_session import (
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_service.application.use_cases.upload_attachment import (
    UploadAttachmentCommand,
    UploadAttachmentHandler,
)
from chat_service.domain.errors import SessionNotFound
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.parse_status import ParseStatus
from media_service.infrastructure.storage.in_memory_object_storage import (
    InMemoryObjectStorage,
)

from tests.conftest import InMemoryAttachmentRepository, InMemorySessionRepository


async def _seed_session(repo: InMemorySessionRepository, config: ModelConfig) -> UUID:
    create = CreateSessionHandler(sessions=repo)
    session = await create.handle(CreateSessionCommand(user_id=uuid4(), config=config))
    return session.id


async def test_unknown_session_raises_session_not_found(
    repo: InMemorySessionRepository,
    attachments: InMemoryAttachmentRepository,
) -> None:
    handler = UploadAttachmentHandler(
        sessions=repo, attachments=attachments, storage=InMemoryObjectStorage()
    )

    with pytest.raises(SessionNotFound):
        await handler.handle(
            UploadAttachmentCommand(
                session_id=uuid4(),
                filename="hi.pdf",
                mime_type="application/pdf",
                data=b"%PDF",
                kind=AttachmentKind.FILE,
            )
        )


async def test_upload_writes_bytes_and_returns_pending_attachment(
    repo: InMemorySessionRepository,
    attachments: InMemoryAttachmentRepository,
    config: ModelConfig,
) -> None:
    session_id = await _seed_session(repo, config)
    storage = InMemoryObjectStorage()
    now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    attachment_id = UUID("11111111-1111-1111-1111-111111111111")
    handler = UploadAttachmentHandler(
        sessions=repo,
        attachments=attachments,
        storage=storage,
        clock=lambda: now,
        id_factory=lambda: attachment_id,
    )

    result = await handler.handle(
        UploadAttachmentCommand(
            session_id=session_id,
            filename="paper.pdf",
            mime_type="application/pdf",
            data=b"%PDFblob",
            kind=AttachmentKind.FILE,
        )
    )

    assert result.attachment.id == attachment_id
    assert result.attachment.session_id == session_id
    assert result.attachment.parse_status is ParseStatus.PENDING
    assert result.attachment.size_bytes == len(b"%PDFblob")
    assert result.attachment.created_at == now

    s3_key = result.attachment.s3_key
    assert s3_key.startswith(f"sessions/{session_id}/attachments/")
    assert s3_key.endswith("/paper.pdf")
    assert await storage.get(key=s3_key) == b"%PDFblob"
    assert storage.content_type(s3_key) == "application/pdf"

    saved = await attachments.get(attachment_id)
    assert saved is not None
    assert saved.parse_status is ParseStatus.PENDING


async def test_voice_upload_uses_audio_kind(
    repo: InMemorySessionRepository,
    attachments: InMemoryAttachmentRepository,
    config: ModelConfig,
) -> None:
    session_id = await _seed_session(repo, config)
    handler = UploadAttachmentHandler(
        sessions=repo, attachments=attachments, storage=InMemoryObjectStorage()
    )

    result = await handler.handle(
        UploadAttachmentCommand(
            session_id=session_id,
            filename="clip.wav",
            mime_type="audio/wav",
            data=b"RIFFblob",
            kind=AttachmentKind.AUDIO,
        )
    )

    assert result.attachment.kind is AttachmentKind.AUDIO
