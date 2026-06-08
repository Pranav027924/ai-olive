"""HTTP tests for the upload endpoints (Phase 6.8).

Dependency overrides swap the real Postgres/MinIO/Whisper adapters
for the in-memory fakes from ``tests/conftest.py`` so these tests
stay unit-fast and don't touch the network.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from chat_service.application.ports.attachment_repository import AttachmentRepository
from chat_service.application.ports.session_repository import SessionRepository
from chat_service.application.use_cases.process_attachment import (
    ProcessAttachmentHandler,
)
from chat_service.application.use_cases.upload_attachment import (
    UploadAttachmentHandler,
)
from chat_service.domain.entities.session import Session
from chat_service.domain.value_objects.model_config import ModelConfig
from chat_service.domain.value_objects.parse_status import ParseStatus
from chat_service.domain.value_objects.session_status import SessionStatus
from chat_service.interfaces.http.app import create_app
from chat_service.interfaces.http.dependencies import (
    get_attachment_repository,
    get_dev_user_id,
    get_process_attachment_handler,
    get_repository,
    get_upload_attachment_handler,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
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

from tests.conftest import (
    InMemoryAttachmentRepository,
    InMemorySessionRepository,
)

DEV_USER = UUID("00000000-0000-0000-0000-000000000001")


class _FakeParser(DocumentParser):
    def __init__(self, *, mime: str, text: str) -> None:
        self._mime = mime
        self._text = text

    @property
    def mime_types(self) -> tuple[str, ...]:
        return (self._mime,)

    async def parse(self, *, document: Document, data: bytes) -> ExtractedContent:
        return ExtractedContent(text=self._text, metadata={"page_count": 1})


class _FakeTranscriber(Transcriber):
    def __init__(self, *, text: str) -> None:
        self._text = text

    async def transcribe(self, *, audio: Audio, data: bytes) -> ExtractedContent:
        return ExtractedContent(text=self._text, metadata={"duration_seconds": 1.0})


@pytest.fixture
def http_repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def http_attachments() -> InMemoryAttachmentRepository:
    return InMemoryAttachmentRepository()


@pytest.fixture
def http_storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


@pytest.fixture
def app(
    http_repo: InMemorySessionRepository,
    http_attachments: InMemoryAttachmentRepository,
    http_storage: InMemoryObjectStorage,
) -> FastAPI:
    app = create_app()
    parser = ParseDocumentHandler(
        registry=ParserRegistry([_FakeParser(mime="application/pdf", text="pdf parsed text")])
    )
    transcriber = TranscribeAudioHandler(transcriber=_FakeTranscriber(text="hi from whisper"))

    def _repo() -> SessionRepository:
        return http_repo

    def _attachments() -> AttachmentRepository:
        return http_attachments

    def _user() -> UUID:
        return DEV_USER

    def _upload() -> UploadAttachmentHandler:
        return UploadAttachmentHandler(
            sessions=http_repo, attachments=http_attachments, storage=http_storage
        )

    def _process() -> ProcessAttachmentHandler:
        return ProcessAttachmentHandler(
            attachments=http_attachments,
            storage=http_storage,
            parser=parser,
            transcriber=transcriber,
        )

    app.dependency_overrides[get_repository] = _repo
    app.dependency_overrides[get_attachment_repository] = _attachments
    app.dependency_overrides[get_dev_user_id] = _user
    app.dependency_overrides[get_upload_attachment_handler] = _upload
    app.dependency_overrides[get_process_attachment_handler] = _process
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _session() -> Session:
    now = datetime(2026, 6, 4, tzinfo=UTC)
    return Session(
        id=uuid4(),
        user_id=DEV_USER,
        title="t",
        system_prompt=None,
        config=ModelConfig(provider="anthropic", model="claude-opus-4-7"),
        status=SessionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        messages=[],
    )


async def _wait_for_terminal_status(
    repo: InMemoryAttachmentRepository, attachment_id: UUID
) -> None:
    for _ in range(50):
        row = await repo.get(attachment_id)
        if row is not None and row.parse_status is not ParseStatus.PENDING:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("attachment never reached a terminal state")


async def test_file_upload_returns_pending_then_completes_via_background(
    client: AsyncClient,
    http_repo: InMemorySessionRepository,
    http_attachments: InMemoryAttachmentRepository,
    http_storage: InMemoryObjectStorage,
) -> None:
    session = _session()
    http_repo.seed([session])

    response = await client.post(
        f"/sessions/{session.id}/files",
        files={"file": ("paper.pdf", b"%PDFblob", "application/pdf")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["session_id"] == str(session.id)
    assert body["kind"] == "file"
    assert body["parse_status"] == "pending"
    attachment_id = UUID(body["id"])

    await _wait_for_terminal_status(http_attachments, attachment_id)
    finished = await http_attachments.get(attachment_id)
    assert finished is not None
    assert finished.parse_status is ParseStatus.COMPLETE
    assert finished.parsed_text == "pdf parsed text"
    assert finished.transcript is None
    assert http_storage.keys() == (finished.s3_key,)


async def test_voice_upload_routes_through_transcriber(
    client: AsyncClient,
    http_repo: InMemorySessionRepository,
    http_attachments: InMemoryAttachmentRepository,
) -> None:
    session = _session()
    http_repo.seed([session])

    response = await client.post(
        f"/sessions/{session.id}/voice",
        files={"file": ("clip.wav", b"RIFFblob", "audio/wav")},
    )

    assert response.status_code == 202
    attachment_id = UUID(response.json()["id"])

    await _wait_for_terminal_status(http_attachments, attachment_id)
    finished = await http_attachments.get(attachment_id)
    assert finished is not None
    assert finished.parse_status is ParseStatus.COMPLETE
    assert finished.transcript == "hi from whisper"
    assert finished.parsed_text is None


async def test_unknown_session_yields_404(
    client: AsyncClient,
) -> None:
    response = await client.post(
        f"/sessions/{uuid4()}/files",
        files={"file": ("paper.pdf", b"%PDF", "application/pdf")},
    )

    assert response.status_code == 404
