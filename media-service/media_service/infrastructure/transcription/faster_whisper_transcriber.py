"""FasterWhisperTranscriber — local Whisper Transcriber (PRD §6.6).

faster-whisper is CTranslate2 under the hood: synchronous and very
CPU-heavy, so we keep the transcribe call inside ``asyncio.to_thread``
and lazy-load the model on first use so importing this module never
forces a download.

For tests we accept a pre-built model object via the ``model`` kwarg —
anything with a ``.transcribe(audio_buffer, ...)`` returning the
``(segments, info)`` pair faster-whisper produces will work, so unit
tests don't need to pull a real ML model.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterable
from typing import Any, Protocol

from media_service.domain.entities.audio import Audio
from media_service.domain.services.transcriber import Transcriber
from media_service.domain.value_objects.extracted_content import ExtractedContent

AUDIO_MIME_TYPES: tuple[str, ...] = (
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/webm",
    "audio/ogg",
)


class _Segment(Protocol):
    text: str


class _TranscribeInfo(Protocol):
    duration: float
    language: str


class _WhisperModelLike(Protocol):
    def transcribe(
        self, audio: Any, **kwargs: Any
    ) -> tuple[Iterable[_Segment], _TranscribeInfo]: ...


class FasterWhisperTranscriber(Transcriber):
    def __init__(
        self,
        *,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        model: _WhisperModelLike | None = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: _WhisperModelLike | None = model

    @property
    def mime_types(self) -> tuple[str, ...]:
        return AUDIO_MIME_TYPES

    async def transcribe(self, *, audio: Audio, data: bytes) -> ExtractedContent:
        model = self._ensure_model()
        text, duration, language = await asyncio.to_thread(_run, model, data)
        return ExtractedContent(
            text=text,
            metadata={
                "filename": audio.filename,
                "duration_seconds": duration,
                "language": language,
                "model": self._model_size,
            },
        )

    def _ensure_model(self) -> _WhisperModelLike:
        if self._model is None:
            from faster_whisper import WhisperModel  # local import: ML deps are heavy

            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )
        return self._model


def _run(model: _WhisperModelLike, data: bytes) -> tuple[str, float, str]:
    segments, info = model.transcribe(io.BytesIO(data))
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    return text, float(info.duration), info.language
