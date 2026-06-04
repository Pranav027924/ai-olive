"""ExtractedContent — value object produced by a parser or transcriber.

Wraps the user-readable ``text`` plus a free-form ``metadata`` dict
where adapters can stash provider-specific extras (page counts,
speaker labels, model confidence, etc.). Immutable, equal-by-value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

_EMPTY: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    text: str
    metadata: Mapping[str, Any] = field(default_factory=lambda: _EMPTY)

    def __len__(self) -> int:
        return len(self.text)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()
