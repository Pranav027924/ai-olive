"""ParseStatus — attachment parse lifecycle (PRD §8.1)."""

from __future__ import annotations

from enum import StrEnum


class ParseStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
