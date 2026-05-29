"""Domain exceptions for the ingestion service.

Raised by the Validator and entities; caught by the HTTP router and
translated to RFC 7807 problem+json (PRD §9.6).
"""

from __future__ import annotations


class IngestionDomainError(Exception):
    """Base class for ingestion domain errors."""


class EmptyBatch(IngestionDomainError):
    """The batch contains zero events."""


class BatchTooLarge(IngestionDomainError):
    """The batch exceeds ``BatchValidator.MAX_BATCH_SIZE``."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"Batch of {size} events exceeds the {limit} cap.")
        self.size = size
        self.limit = limit
