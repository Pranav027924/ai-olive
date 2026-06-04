"""Document entity — a file ready to be parsed (PRD §5.3, §6.5).

The bytes themselves are kept out of the entity so domain code stays
allocation-light. The use case loads the blob from storage and hands
both ``Document`` and the raw bytes to the parser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Document:
    filename: str
    mime_type: str
    size_bytes: int
