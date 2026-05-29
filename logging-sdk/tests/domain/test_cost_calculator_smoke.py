"""Smoke test for the CostCalculator domain service (Phase 3.2).

Locks in the public surface so subsequent commits can't accidentally
rename. Exhaustive table-coverage and unknown-model behaviour land
in Phase 3.3.
"""

from __future__ import annotations

from decimal import Decimal

from olive_sdk.domain.services.cost_calculator import CostCalculator


def test_returns_decimal_for_known_anthropic_model() -> None:
    calc = CostCalculator()
    out = calc.estimate(
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert isinstance(out, Decimal)
    assert out > Decimal("0")


def test_returns_none_for_unknown_model() -> None:
    calc = CostCalculator()
    out = calc.estimate(
        provider="anthropic",
        model="claude-from-the-future-9000",
        prompt_tokens=100,
        completion_tokens=100,
    )
    assert out is None
