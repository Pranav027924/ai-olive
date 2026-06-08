"""AttachmentRepository — outbound port for Attachment persistence."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from chat_service.domain.entities.attachment import Attachment


class AttachmentRepository(Protocol):
    async def save(self, attachment: Attachment) -> None:
        """Insert or update the row backing ``attachment``."""

    async def get(self, attachment_id: UUID) -> Attachment | None:
        """Return the attachment with this id, or ``None`` if absent."""

    async def list_for_session(self, session_id: UUID) -> list[Attachment]:
        """Return every attachment bound to ``session_id`` in created_at order."""
