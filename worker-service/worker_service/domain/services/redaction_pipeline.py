"""RedactionPipeline — chain-of-responsibility over Redactors (PRD §6.4, §10.2).

Each redactor sees the output of the previous one. The pipeline is
ordered; users typically place the cheapest patterns first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class Redactor(Protocol):
    """A small functor that replaces sensitive substrings."""

    def redact(self, text: str) -> str: ...


@dataclass(frozen=True, slots=True)
class RedactionPipeline:
    redactors: tuple[Redactor, ...] = field(default_factory=tuple)

    def redact(self, text: str) -> str:
        for r in self.redactors:
            text = r.redact(text)
        return text
