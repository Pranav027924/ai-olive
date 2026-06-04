"""DocumentParser — outbound port for media-service parsers (PRD §6.5).

Concrete implementations live under
``media_service.infrastructure.parsing`` (pypdf, python-docx, ...).
The Strategy-pattern registry in Phase 6.3 routes by ``mime_type``.
"""

from __future__ import annotations

from typing import Protocol

from media_service.domain.entities.document import Document
from media_service.domain.value_objects.extracted_content import ExtractedContent


class DocumentParser(Protocol):
    """Parses document bytes into ExtractedContent."""

    @property
    def mime_types(self) -> tuple[str, ...]:
        """MIME types this parser handles (e.g. ``("application/pdf",)``)."""

    async def parse(self, *, document: Document, data: bytes) -> ExtractedContent:
        """Return text extracted from ``data``."""
