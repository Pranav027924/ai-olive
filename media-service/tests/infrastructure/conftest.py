"""Fixture blobs for parser integration tests (Phase 6.4).

PDF + DOCX bytes are minted at test time with reportlab / python-docx
so we never check binary fixtures into git. Each fixture pair (bytes
+ known text) is exposed separately so tests can assert against the
exact strings the fixture wrote — no cross-module imports required.
"""

from __future__ import annotations

import io

import pytest
from docx import Document as DocxDocument
from reportlab.pdfgen.canvas import Canvas


@pytest.fixture
def pdf_page_texts() -> tuple[str, ...]:
    return ("Olive AI greets you", "Second page sentinel")


@pytest.fixture
def pdf_bytes(pdf_page_texts: tuple[str, ...]) -> bytes:
    buf = io.BytesIO()
    canvas = Canvas(buf)
    for text in pdf_page_texts:
        canvas.drawString(100, 750, text)
        canvas.showPage()
    canvas.save()
    return buf.getvalue()


@pytest.fixture
def docx_paragraphs() -> tuple[str, ...]:
    return ("Olive AI greets you", "Second paragraph sentinel")


@pytest.fixture
def docx_bytes(docx_paragraphs: tuple[str, ...]) -> bytes:
    docx = DocxDocument()
    for paragraph in docx_paragraphs:
        docx.add_paragraph(paragraph)
    buf = io.BytesIO()
    docx.save(buf)
    return buf.getvalue()
