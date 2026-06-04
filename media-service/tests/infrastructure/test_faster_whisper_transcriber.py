"""Tests for FasterWhisperTranscriber (Phase 6.6).

Real Whisper model downloads are skipped here — the adapter takes a
``model`` kwarg specifically so we can inject a fake without pulling
a 75 MB CTranslate2 model into CI. The end-to-end test in Phase 6.11
exercises the real model against a generated audio clip.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from media_service.domain.entities.audio import Audio
from media_service.infrastructure.transcription.faster_whisper_transcriber import (
    AUDIO_MIME_TYPES,
    FasterWhisperTranscriber,
)


@dataclass
class _FakeSegment:
    text: str


@dataclass
class _FakeInfo:
    duration: float
    language: str


class _FakeModel:
    def __init__(self, *, segments: list[str], duration: float, language: str) -> None:
        self._segments = [_FakeSegment(text=s) for s in segments]
        self._info = _FakeInfo(duration=duration, language=language)
        self.calls: list[bytes] = []

    def transcribe(self, audio: Any, **_: Any) -> tuple[list[_FakeSegment], _FakeInfo]:
        assert isinstance(audio, io.BytesIO)
        self.calls.append(audio.getvalue())
        return self._segments, self._info


def _audio() -> Audio:
    return Audio(filename="clip.wav", mime_type="audio/wav", size_bytes=8)


def test_transcriber_advertises_common_audio_mime_types() -> None:
    assert "audio/wav" in AUDIO_MIME_TYPES
    assert "audio/mpeg" in AUDIO_MIME_TYPES
    assert FasterWhisperTranscriber().mime_types == AUDIO_MIME_TYPES


async def test_transcriber_joins_segments_and_returns_extracted_content() -> None:
    model = _FakeModel(
        segments=[" Hello", " world", " "],  # whitespace-only segments are dropped
        duration=3.5,
        language="en",
    )
    transcriber = FasterWhisperTranscriber(model=model)

    result = await transcriber.transcribe(audio=_audio(), data=b"RIFFDATA")

    assert result.text == "Hello world"
    assert result.metadata["duration_seconds"] == 3.5
    assert result.metadata["language"] == "en"
    assert result.metadata["filename"] == "clip.wav"
    assert result.metadata["model"] == "tiny"
    assert model.calls == [b"RIFFDATA"]


async def test_transcriber_records_configured_model_size_in_metadata() -> None:
    model = _FakeModel(segments=["hi"], duration=1.0, language="en")
    transcriber = FasterWhisperTranscriber(model_size="base", model=model)

    result = await transcriber.transcribe(audio=_audio(), data=b"x")

    assert result.metadata["model"] == "base"


async def test_empty_segments_produce_empty_text() -> None:
    """Whisper returning silence is the transcriber's "no speech"
    signal. The application-layer TranscribeAudioHandler turns that
    into TranscriptionFailed; here we just verify the adapter passes
    the empty string up faithfully."""
    transcriber = FasterWhisperTranscriber(
        model=_FakeModel(segments=[], duration=0.5, language="en")
    )

    result = await transcriber.transcribe(audio=_audio(), data=b"x")

    assert result.text == ""
    assert result.is_empty
