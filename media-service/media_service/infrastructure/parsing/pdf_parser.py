"""PdfParser — pypdf-based DocumentParser (PRD §6.4).

Wraps :class:`pypdf.PdfReader` in an ``asyncio.to_thread`` call so
the parse step doesn't block the event loop while pypdf is doing
CPU-bound extraction. ``page_count`` is exposed via the
ExtractedContent.metadata so the chat UI can show "Parsed 3 pages".
"""

from __future__ import annotations

import asyncio
import io

from pypdf import PdfReader

from media_service.domain.entities.document import Document
from media_service.domain.services.document_parser import DocumentParser
from media_service.domain.value_objects.extracted_content import ExtractedContent

PDF_MIME_TYPES: tuple[str, ...] = ("application/pdf",)


class PdfParser(DocumentParser):
    @property
    def mime_types(self) -> tuple[str, ...]:
        return PDF_MIME_TYPES

    async def parse(self, *, document: Document, data: bytes) -> ExtractedContent:
        text, page_count = await asyncio.to_thread(_extract_text, data)
        return ExtractedContent(
            text=text,
            metadata={"page_count": page_count, "filename": document.filename},
        )


def _extract_text(data: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(data))
    pages = list(reader.pages)
    text_parts = [page.extract_text() or "" for page in pages]
    joined = "\n".join(part.strip() for part in text_parts if part.strip())
    return joined, len(pages)
