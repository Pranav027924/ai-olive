"""PostgresAttachmentRepository — :class:`AttachmentRepository` adapter."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chat_service.application.ports.attachment_repository import AttachmentRepository
from chat_service.domain.entities.attachment import Attachment
from chat_service.domain.value_objects.attachment_kind import AttachmentKind
from chat_service.domain.value_objects.parse_status import ParseStatus

from .sqlalchemy_models import AttachmentRow


class PostgresAttachmentRepository(AttachmentRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, attachment_id: UUID) -> Attachment | None:
        async with self._sessionmaker() as db:
            row = await db.scalar(select(AttachmentRow).where(AttachmentRow.id == attachment_id))
            return _row_to_domain(row) if row else None

    async def list_for_session(self, session_id: UUID) -> list[Attachment]:
        async with self._sessionmaker() as db:
            rows = (
                await db.scalars(
                    select(AttachmentRow)
                    .where(AttachmentRow.session_id == session_id)
                    .order_by(AttachmentRow.created_at.asc())
                )
            ).all()
            return [_row_to_domain(r) for r in rows]

    async def save(self, attachment: Attachment) -> None:
        async with self._sessionmaker() as db, db.begin():
            row = await db.scalar(select(AttachmentRow).where(AttachmentRow.id == attachment.id))
            if row is None:
                db.add(
                    AttachmentRow(
                        id=attachment.id,
                        session_id=attachment.session_id,
                        message_id=attachment.message_id,
                        kind=attachment.kind.value,
                        filename=attachment.filename,
                        mime_type=attachment.mime_type,
                        size_bytes=attachment.size_bytes,
                        s3_key=attachment.s3_key,
                        parse_status=attachment.parse_status.value,
                        parsed_text=attachment.parsed_text,
                        transcript=attachment.transcript,
                        created_at=attachment.created_at,
                    )
                )
            else:
                row.message_id = attachment.message_id
                row.parse_status = attachment.parse_status.value
                row.parsed_text = attachment.parsed_text
                row.transcript = attachment.transcript


def _row_to_domain(row: AttachmentRow) -> Attachment:
    return Attachment(
        id=row.id,
        session_id=row.session_id,
        message_id=row.message_id,
        kind=AttachmentKind(row.kind),
        filename=row.filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        s3_key=row.s3_key,
        parse_status=ParseStatus(row.parse_status),
        parsed_text=row.parsed_text,
        transcript=row.transcript,
        created_at=row.created_at,
    )
