"""Attachments router — file + voice uploads (PRD §6.8).

The synchronous request:
1. Validates the session exists (via the use case).
2. Persists the bytes to ObjectStorage and the row to Postgres.
3. Returns 202 Accepted with the pending attachment.

The asynchronous parse/transcribe runs as a FastAPI BackgroundTask
inside the same process, so the response can return immediately
while the heavy work runs in the event loop.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from chat_service.application.use_cases.process_attachment import ProcessAttachmentCommand
from chat_service.application.use_cases.upload_attachment import UploadAttachmentCommand
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.interfaces.http.dependencies import (
    ProcessAttachmentDep,
    UploadAttachmentDep,
)
from chat_service.interfaces.http.schemas import AttachmentView

router = APIRouter(prefix="/sessions", tags=["attachments"])


@router.post(
    "/{session_id}/files",
    response_model=AttachmentView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_file(
    session_id: UUID,
    upload: UploadAttachmentDep,
    processor: ProcessAttachmentDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
) -> AttachmentView:
    if not file.filename or not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file must include a filename and Content-Type",
        )
    data = await file.read()
    result = await upload.handle(
        UploadAttachmentCommand(
            session_id=session_id,
            filename=file.filename,
            mime_type=file.content_type,
            data=data,
            kind=AttachmentKind.FILE,
        )
    )
    background.add_task(
        processor.handle, ProcessAttachmentCommand(attachment_id=result.attachment.id)
    )
    return AttachmentView.from_domain(result.attachment)


@router.post(
    "/{session_id}/voice",
    response_model=AttachmentView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_voice(
    session_id: UUID,
    upload: UploadAttachmentDep,
    processor: ProcessAttachmentDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
) -> AttachmentView:
    if not file.filename or not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file must include a filename and Content-Type",
        )
    data = await file.read()
    result = await upload.handle(
        UploadAttachmentCommand(
            session_id=session_id,
            filename=file.filename,
            mime_type=file.content_type,
            data=data,
            kind=AttachmentKind.AUDIO,
        )
    )
    background.add_task(
        processor.handle, ProcessAttachmentCommand(attachment_id=result.attachment.id)
    )
    return AttachmentView.from_domain(result.attachment)
