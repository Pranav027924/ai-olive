"""Integration tests for PdfParser + DocxParser (Phase 6.4).

These tests run the real pypdf / python-docx code paths against
in-memory blobs minted in conftest.py, then verify both adapters
also work end-to-end via the ParserRegistry (so we don't accidentally
ship a parser that the registry can't route to).
"""

from __future__ import annotations

import pytest
from media_service.application.use_cases.parse_document import (
    ParseDocumentCommand,
    ParseDocumentHandler,
    ParserRegistry,
)
from media_service.domain.entities.document import Document
from media_service.infrastructure.parsing.docx_parser import DOCX_MIME_TYPES, DocxParser
from media_service.infrastructure.parsing.pdf_parser import PDF_MIME_TYPES, PdfParser

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _pdf_doc(size: int) -> Document:
    return Document(filename="hello.pdf", mime_type=PDF_MIME, size_bytes=size)


def _docx_doc(size: int) -> Document:
    return Document(filename="hello.docx", mime_type=DOCX_MIME, size_bytes=size)


# ---------------------------------------------------------------------------
# PdfParser
# ---------------------------------------------------------------------------


def test_pdf_parser_advertises_pdf_mime() -> None:
    assert PdfParser().mime_types == PDF_MIME_TYPES == (PDF_MIME,)


async def test_pdf_parser_extracts_text_from_every_page(
    pdf_bytes: bytes, pdf_page_texts: tuple[str, ...]
) -> None:
    result = await PdfParser().parse(document=_pdf_doc(len(pdf_bytes)), data=pdf_bytes)

    for expected in pdf_page_texts:
        assert expected in result.text


async def test_pdf_parser_reports_page_count_and_filename(
    pdf_bytes: bytes, pdf_page_texts: tuple[str, ...]
) -> None:
    result = await PdfParser().parse(document=_pdf_doc(len(pdf_bytes)), data=pdf_bytes)

    assert result.metadata["page_count"] == len(pdf_page_texts)
    assert result.metadata["filename"] == "hello.pdf"


# ---------------------------------------------------------------------------
# DocxParser
# ---------------------------------------------------------------------------


def test_docx_parser_advertises_docx_mime() -> None:
    assert DocxParser().mime_types == DOCX_MIME_TYPES == (DOCX_MIME,)


async def test_docx_parser_extracts_each_paragraph(
    docx_bytes: bytes, docx_paragraphs: tuple[str, ...]
) -> None:
    result = await DocxParser().parse(document=_docx_doc(len(docx_bytes)), data=docx_bytes)

    for paragraph in docx_paragraphs:
        assert paragraph in result.text


async def test_docx_parser_reports_paragraph_count_and_filename(
    docx_bytes: bytes, docx_paragraphs: tuple[str, ...]
) -> None:
    result = await DocxParser().parse(document=_docx_doc(len(docx_bytes)), data=docx_bytes)

    assert result.metadata["paragraph_count"] == len(docx_paragraphs)
    assert result.metadata["filename"] == "hello.docx"


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def handler() -> ParseDocumentHandler:
    return ParseDocumentHandler(registry=ParserRegistry([PdfParser(), DocxParser()]))


async def test_registry_routes_pdf_through_pdf_parser(
    handler: ParseDocumentHandler,
    pdf_bytes: bytes,
    pdf_page_texts: tuple[str, ...],
) -> None:
    result = await handler.handle(
        ParseDocumentCommand(document=_pdf_doc(len(pdf_bytes)), data=pdf_bytes)
    )
    assert pdf_page_texts[0] in result.content.text
    assert result.content.metadata["page_count"] == len(pdf_page_texts)


async def test_registry_routes_docx_through_docx_parser(
    handler: ParseDocumentHandler,
    docx_bytes: bytes,
    docx_paragraphs: tuple[str, ...],
) -> None:
    result = await handler.handle(
        ParseDocumentCommand(document=_docx_doc(len(docx_bytes)), data=docx_bytes)
    )
    assert docx_paragraphs[0] in result.content.text
    assert result.content.metadata["paragraph_count"] == len(docx_paragraphs)
