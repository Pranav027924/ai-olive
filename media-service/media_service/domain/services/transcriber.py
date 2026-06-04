"""Transcriber — outbound port for media-service transcription (PRD §6.5).

Phase 6.6 ships the faster-whisper adapter. Future providers (OpenAI
Whisper API, AssemblyAI, ...) plug in here without changing the
application layer.
"""

from __future__ import annotations

from typing import Protocol

from media_service.domain.entities.audio import Audio
from media_service.domain.value_objects.extracted_content import ExtractedContent


class Transcriber(Protocol):
    async def transcribe(self, *, audio: Audio, data: bytes) -> ExtractedContent:
        """Return the spoken text in ``data``."""
