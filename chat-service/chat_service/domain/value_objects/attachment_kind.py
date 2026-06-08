"""AttachmentKind — file/audio/image classifier (PRD §8.1)."""

from __future__ import annotations

from enum import StrEnum


class AttachmentKind(StrEnum):
    FILE = "file"
    AUDIO = "audio"
    IMAGE = "image"
