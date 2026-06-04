"""DocxParser — python-docx DocumentParser (PRD §6.4).

Mirrors :class:`PdfParser`: the synchronous python-docx work runs
inside ``asyncio.to_thread`` so the event loop stays responsive
during extraction.
"""

from __future__ import annotations

import asyncio
import io

from docx import Document as DocxDocument

from media_service.domain.entities.document import Document
from media_service.domain.services.document_parser import DocumentParser
from media_service.domain.value_objects.extracted_content import ExtractedContent

DOCX_MIME_TYPES: tuple[str, ...] = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)


class DocxParser(DocumentParser):
    @property
    def mime_types(self) -> tuple[str, ...]:
        return DOCX_MIME_TYPES

    async def parse(self, *, document: Document, data: bytes) -> ExtractedContent:
        text, paragraph_count = await asyncio.to_thread(_extract_text, data)
        return ExtractedContent(
            text=text,
            metadata={
                "paragraph_count": paragraph_count,
                "filename": document.filename,
            },
        )


def _extract_text(data: bytes) -> tuple[str, int]:
    docx = DocxDocument(io.BytesIO(data))
    paragraphs = [p.text.strip() for p in docx.paragraphs if p.text.strip()]
    return "\n".join(paragraphs), len(paragraphs)
