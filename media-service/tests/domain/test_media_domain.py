"""Tests for the media-service domain types (Phase 6.2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from media_service.domain.entities.audio import Audio
from media_service.domain.entities.document import Document
from media_service.domain.value_objects.extracted_content import ExtractedContent

# ---------------------------------------------------------------------------
# Document / Audio
# ---------------------------------------------------------------------------


def test_document_fields() -> None:
    d = Document(filename="report.pdf", mime_type="application/pdf", size_bytes=12345)
    assert d.filename == "report.pdf"
    assert d.mime_type == "application/pdf"
    assert d.size_bytes == 12345


def test_document_is_frozen() -> None:
    d = Document(filename="r.pdf", mime_type="application/pdf", size_bytes=1)
    with pytest.raises(FrozenInstanceError):
        d.filename = "other.pdf"  # type: ignore[misc]


def test_audio_optional_duration_defaults_to_none() -> None:
    a = Audio(filename="hi.webm", mime_type="audio/webm", size_bytes=50_000)
    assert a.duration_seconds is None


def test_audio_records_duration_when_provided() -> None:
    a = Audio(
        filename="speech.wav",
        mime_type="audio/wav",
        size_bytes=200_000,
        duration_seconds=4.2,
    )
    assert a.duration_seconds == 4.2


# ---------------------------------------------------------------------------
# ExtractedContent
# ---------------------------------------------------------------------------


def test_extracted_content_defaults() -> None:
    c = ExtractedContent(text="hello world")
    assert c.text == "hello world"
    assert len(c) == 11
    assert c.is_empty is False
    assert dict(c.metadata) == {}


def test_extracted_content_metadata_is_preserved() -> None:
    c = ExtractedContent(text="x", metadata={"pages": 3, "ocr": False})
    assert c.metadata["pages"] == 3
    assert c.metadata["ocr"] is False


def test_extracted_content_is_empty_for_whitespace_only_text() -> None:
    assert ExtractedContent(text="").is_empty is True
    assert ExtractedContent(text="   \n\t").is_empty is True


def test_extracted_content_equality_is_by_value() -> None:
    a = ExtractedContent(text="x", metadata={"k": 1})
    b = ExtractedContent(text="x", metadata={"k": 1})
    assert a == b


def test_extracted_content_is_frozen() -> None:
    c = ExtractedContent(text="hi")
    with pytest.raises(FrozenInstanceError):
        c.text = "bye"  # type: ignore[misc]
