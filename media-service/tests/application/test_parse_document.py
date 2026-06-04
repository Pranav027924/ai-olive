"""Tests for ParseDocumentHandler + ParserRegistry (Phase 6.3)."""

from __future__ import annotations

import pytest
from media_service.application.use_cases.parse_document import (
    ParseDocumentCommand,
    ParseDocumentHandler,
    ParserRegistry,
)
from media_service.domain.entities.document import Document
from media_service.domain.errors import UnsupportedMimeType
from media_service.domain.services.document_parser import DocumentParser
from media_service.domain.value_objects.extracted_content import ExtractedContent


class _FakeParser(DocumentParser):
    def __init__(
        self,
        *,
        mime_types: tuple[str, ...],
        produces: str = "fake-output",
    ) -> None:
        self._mime_types = mime_types
        self._produces = produces
        self.calls: list[tuple[Document, bytes]] = []

    @property
    def mime_types(self) -> tuple[str, ...]:
        return self._mime_types

    async def parse(self, *, document: Document, data: bytes) -> ExtractedContent:
        self.calls.append((document, data))
        return ExtractedContent(text=self._produces, metadata={"mime": document.mime_type})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_routes_by_mime_type() -> None:
    a = _FakeParser(mime_types=("application/pdf",))
    b = _FakeParser(
        mime_types=("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    )
    registry = ParserRegistry([a, b])

    assert registry.parser_for("application/pdf") is a
    assert (
        registry.parser_for(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        is b
    )


def test_registry_handles_parser_with_multiple_mimes() -> None:
    multi = _FakeParser(mime_types=("text/plain", "text/markdown"))
    registry = ParserRegistry([multi])
    assert registry.parser_for("text/plain") is multi
    assert registry.parser_for("text/markdown") is multi


def test_registry_supported_mime_types_is_sorted() -> None:
    a = _FakeParser(mime_types=("z/zzz",))
    b = _FakeParser(mime_types=("a/aaa",))
    registry = ParserRegistry([a, b])
    assert registry.supported_mime_types() == ("a/aaa", "z/zzz")


def test_unknown_mime_returns_none() -> None:
    registry = ParserRegistry([_FakeParser(mime_types=("application/pdf",))])
    assert registry.parser_for("image/png") is None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


async def test_handler_delegates_to_the_right_parser() -> None:
    pdf = _FakeParser(mime_types=("application/pdf",), produces="pdf-text")
    docx = _FakeParser(
        mime_types=("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
        produces="docx-text",
    )
    handler = ParseDocumentHandler(registry=ParserRegistry([pdf, docx]))

    result = await handler.handle(
        ParseDocumentCommand(
            document=Document(filename="r.pdf", mime_type="application/pdf", size_bytes=10),
            data=b"%PDF-1.4",
        )
    )

    assert result.content.text == "pdf-text"
    assert pdf.calls == [
        (Document(filename="r.pdf", mime_type="application/pdf", size_bytes=10), b"%PDF-1.4"),
    ]
    assert docx.calls == []


async def test_handler_raises_unsupported_mime_type_with_supported_list() -> None:
    pdf = _FakeParser(mime_types=("application/pdf",))
    handler = ParseDocumentHandler(registry=ParserRegistry([pdf]))

    with pytest.raises(UnsupportedMimeType) as exc:
        await handler.handle(
            ParseDocumentCommand(
                document=Document(filename="a.png", mime_type="image/png", size_bytes=1),
                data=b"\x89PNG",
            )
        )
    assert exc.value.mime_type == "image/png"
    assert exc.value.supported == ("application/pdf",)


async def test_handler_returns_extracted_content_with_metadata() -> None:
    pdf = _FakeParser(mime_types=("application/pdf",), produces="hello")
    handler = ParseDocumentHandler(registry=ParserRegistry([pdf]))

    result = await handler.handle(
        ParseDocumentCommand(
            document=Document(filename="r.pdf", mime_type="application/pdf", size_bytes=10),
            data=b"%PDF-1.4",
        )
    )

    assert result.content.text == "hello"
    assert result.content.metadata == {"mime": "application/pdf"}
