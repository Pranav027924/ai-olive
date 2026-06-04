"""Media-service domain errors."""

from __future__ import annotations


class MediaDomainError(Exception):
    """Base class for media-service domain errors."""


class UnsupportedMimeType(MediaDomainError):
    """No parser in the registry handles this MIME type."""

    def __init__(self, mime_type: str, supported: tuple[str, ...]) -> None:
        super().__init__(
            f"No parser registered for {mime_type!r}. Supported: {supported}",
        )
        self.mime_type = mime_type
        self.supported = supported


class ParseFailed(MediaDomainError):
    """Parsing succeeded structurally but yielded no usable text."""


class TranscriptionFailed(MediaDomainError):
    """Transcription returned an empty or otherwise unusable result."""
