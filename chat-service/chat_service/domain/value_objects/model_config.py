"""ModelConfig — provider + model pair for a session.

Immutable value object. Equality by value. The provider is kept as a
plain ``str`` rather than the wire-format ``Provider`` literal so the
domain isn't forced to widen whenever a new provider is added — the
HTTP layer validates the literal at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """LLM provider and model identifier."""

    provider: str
    model: str
