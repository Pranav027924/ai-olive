"""Tests for TranscribeAudioHandler (Phase 6.5)."""

from __future__ import annotations

import pytest
from media_service.application.use_cases.transcribe_audio import (
    TranscribeAudioCommand,
    TranscribeAudioHandler,
)
from media_service.domain.entities.audio import Audio
from media_service.domain.errors import TranscriptionFailed
from media_service.domain.services.transcriber import Transcriber
from media_service.domain.value_objects.extracted_content import ExtractedContent


class _FakeTranscriber(Transcriber):
    def __init__(self, *, text: str = "hello world", duration: float | None = 1.5) -> None:
        self._text = text
        self._duration = duration
        self.calls: list[tuple[Audio, bytes]] = []

    async def transcribe(self, *, audio: Audio, data: bytes) -> ExtractedContent:
        self.calls.append((audio, data))
        metadata: dict[str, object] = {"filename": audio.filename}
        if self._duration is not None:
            metadata["duration_seconds"] = self._duration
        return ExtractedContent(text=self._text, metadata=metadata)


def _audio() -> Audio:
    return Audio(filename="clip.wav", mime_type="audio/wav", size_bytes=42)


async def test_handler_delegates_to_transcriber() -> None:
    transcriber = _FakeTranscriber(text="spoken text")
    handler = TranscribeAudioHandler(transcriber=transcriber)

    result = await handler.handle(TranscribeAudioCommand(audio=_audio(), data=b"RIFF...."))

    assert result.content.text == "spoken text"
    assert transcriber.calls == [(_audio(), b"RIFF....")]


async def test_handler_propagates_transcriber_metadata() -> None:
    transcriber = _FakeTranscriber(duration=12.25)
    handler = TranscribeAudioHandler(transcriber=transcriber)

    result = await handler.handle(TranscribeAudioCommand(audio=_audio(), data=b"x"))

    assert result.content.metadata["duration_seconds"] == 12.25
    assert result.content.metadata["filename"] == "clip.wav"


async def test_empty_transcript_raises_transcription_failed() -> None:
    handler = TranscribeAudioHandler(transcriber=_FakeTranscriber(text="   "))

    with pytest.raises(TranscriptionFailed):
        await handler.handle(TranscribeAudioCommand(audio=_audio(), data=b"x"))


async def test_whitespace_only_transcript_raises_transcription_failed() -> None:
    """ExtractedContent treats whitespace-only as empty; the use case
    must surface that as TranscriptionFailed instead of letting a
    blank transcript reach the LLM context."""
    handler = TranscribeAudioHandler(transcriber=_FakeTranscriber(text=""))

    with pytest.raises(TranscriptionFailed) as exc:
        await handler.handle(TranscribeAudioCommand(audio=_audio(), data=b"x"))

    assert "clip.wav" in str(exc.value)
