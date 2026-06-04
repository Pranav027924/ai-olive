"""Audio entity — a clip ready to be transcribed (PRD §5.3, §6.5).

``duration_seconds`` is optional — populated lazily by the
transcriber when it inspects the bytes; the use case doesn't have
to know about it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Audio:
    filename: str
    mime_type: str
    size_bytes: int
    duration_seconds: float | None = None
