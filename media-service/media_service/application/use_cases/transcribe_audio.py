"""TranscribeAudio — single-port use case (PRD §6.5, §10.2).

Sits between the chat-service upload endpoint and whatever
transcription backend is wired up at startup (faster-whisper today,
remote APIs tomorrow). The use case never imports concrete adapters
— a :class:`Transcriber` is injected at construction time.

An empty transcript is treated as failure: returning a blank string
would silently pollute the LLM prompt with nothing useful, so we
raise :class:`TranscriptionFailed` and let the caller mark the
attachment ``parse_status='failed'``.
"""

from __future__ import annotations

from dataclasses import dataclass

from media_service.domain.entities.audio import Audio
from media_service.domain.errors import TranscriptionFailed
from media_service.domain.services.transcriber import Transcriber
from media_service.domain.value_objects.extracted_content import ExtractedContent


@dataclass(frozen=True, slots=True)
class TranscribeAudioCommand:
    audio: Audio
    data: bytes


@dataclass(frozen=True, slots=True)
class TranscribeAudioResult:
    content: ExtractedContent


class TranscribeAudioHandler:
    def __init__(self, *, transcriber: Transcriber) -> None:
        self._transcriber = transcriber

    async def handle(self, cmd: TranscribeAudioCommand) -> TranscribeAudioResult:
        content = await self._transcriber.transcribe(audio=cmd.audio, data=cmd.data)
        if content.is_empty:
            raise TranscriptionFailed(
                f"Transcriber returned empty content for {cmd.audio.filename!r}"
            )
        return TranscribeAudioResult(content=content)
