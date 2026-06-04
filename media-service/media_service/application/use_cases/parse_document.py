"""ParseDocument — MIME-keyed strategy use case (PRD §6.3, §10.2).

Routes a Document + bytes to the right DocumentParser based on the
``mime_type`` and returns the resulting ExtractedContent. New
parsers are added by handing them to the ParserRegistry; the use
case itself never imports the concrete adapters.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from media_service.domain.entities.document import Document
from media_service.domain.errors import UnsupportedMimeType
from media_service.domain.services.document_parser import DocumentParser
from media_service.domain.value_objects.extracted_content import ExtractedContent


class ParserRegistry:
    def __init__(self, parsers: Iterable[DocumentParser]) -> None:
        by_mime: dict[str, DocumentParser] = {}
        for parser in parsers:
            for mime in parser.mime_types:
                by_mime[mime] = parser
        self._by_mime = by_mime

    def parser_for(self, mime_type: str) -> DocumentParser | None:
        return self._by_mime.get(mime_type)

    def supported_mime_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_mime.keys()))


@dataclass(frozen=True, slots=True)
class ParseDocumentCommand:
    document: Document
    data: bytes


@dataclass(frozen=True, slots=True)
class ParseDocumentResult:
    content: ExtractedContent


class ParseDocumentHandler:
    def __init__(self, *, registry: ParserRegistry) -> None:
        self._registry = registry

    async def handle(self, cmd: ParseDocumentCommand) -> ParseDocumentResult:
        parser = self._registry.parser_for(cmd.document.mime_type)
        if parser is None:
            raise UnsupportedMimeType(
                cmd.document.mime_type,
                self._registry.supported_mime_types(),
            )
        content = await parser.parse(document=cmd.document, data=cmd.data)
        return ParseDocumentResult(content=content)
