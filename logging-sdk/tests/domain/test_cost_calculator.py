"""Exhaustive tests for CostCalculator (Phase 3.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from olive_sdk.domain.services.cost_calculator import CostCalculator, Rate


def _calc() -> CostCalculator:
    return CostCalculator()


# ---------------------------------------------------------------------------
# Arithmetic — exact decimals
# ---------------------------------------------------------------------------


def test_one_million_prompt_tokens_for_opus_costs_15_usd() -> None:
    """Anthropic claude-opus-4-7 input rate is $15 / 1M tokens."""
    out = _calc().estimate(
        provider="anthropic", model="claude-opus-4-7", prompt_tokens=1_000_000, completion_tokens=0
    )
    assert out == Decimal("15")


def test_one_million_completion_tokens_for_opus_costs_75_usd() -> None:
    """Anthropic claude-opus-4-7 output rate is $75 / 1M tokens."""
    out = _calc().estimate(
        provider="anthropic", model="claude-opus-4-7", prompt_tokens=0, completion_tokens=1_000_000
    )
    assert out == Decimal("75")


def test_mixed_tokens_for_opus() -> None:
    """1k prompt + 500 completion = (1000 * 15 + 500 * 75) / 1_000_000 = $0.0525."""
    out = _calc().estimate(
        provider="anthropic", model="claude-opus-4-7", prompt_tokens=1000, completion_tokens=500
    )
    assert out == Decimal("0.052500")


def test_sonnet_is_cheaper_than_opus_for_the_same_volume() -> None:
    sonnet = _calc().estimate(
        provider="anthropic",
        model="claude-sonnet-4-6",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )
    opus = _calc().estimate(
        provider="anthropic", model="claude-opus-4-7", prompt_tokens=1_000_000, completion_tokens=0
    )
    assert sonnet is not None
    assert opus is not None
    assert sonnet < opus


def test_haiku_is_cheaper_than_sonnet_for_the_same_volume() -> None:
    haiku = _calc().estimate(
        provider="anthropic",
        model="claude-haiku-4-5",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )
    sonnet = _calc().estimate(
        provider="anthropic",
        model="claude-sonnet-4-6",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )
    assert haiku is not None
    assert sonnet is not None
    assert haiku < sonnet


def test_zero_tokens_yields_zero_cost() -> None:
    out = _calc().estimate(
        provider="anthropic", model="claude-opus-4-7", prompt_tokens=0, completion_tokens=0
    )
    assert out == Decimal("0")


# ---------------------------------------------------------------------------
# None token counts
# ---------------------------------------------------------------------------


def test_none_prompt_tokens_is_treated_as_zero() -> None:
    out = _calc().estimate(
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_tokens=None,
        completion_tokens=100,
    )
    assert out is not None
    # 0 input + 100 output * 75/1M = $0.0075
    assert out == Decimal("0.007500")


def test_both_none_yields_zero_for_known_model() -> None:
    out = _calc().estimate(
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_tokens=None,
        completion_tokens=None,
    )
    assert out == Decimal("0")


# ---------------------------------------------------------------------------
# Unknown / unsupported models
# ---------------------------------------------------------------------------


def test_unknown_model_returns_none() -> None:
    out = _calc().estimate(
        provider="anthropic",
        model="claude-not-a-real-model",
        prompt_tokens=100,
        completion_tokens=100,
    )
    assert out is None


def test_known_model_under_wrong_provider_returns_none() -> None:
    # The same model name under a different provider doesn't match.
    out = _calc().estimate(
        provider="openai",
        model="claude-opus-4-7",
        prompt_tokens=100,
        completion_tokens=100,
    )
    assert out is None


@pytest.mark.parametrize("provider", ["openai", "gemini", "deepseek"])
def test_other_providers_unsupported_in_phase_3(provider: str) -> None:
    """OpenAI / Gemini / DeepSeek adapters land in Phase 7.1 alongside their rates."""
    out = _calc().estimate(
        provider=provider, model="gpt-4o", prompt_tokens=100, completion_tokens=100
    )
    assert out is None


# ---------------------------------------------------------------------------
# Table contents
# ---------------------------------------------------------------------------


def test_supported_models_lists_every_seeded_pair() -> None:
    models = CostCalculator.supported_models()
    assert ("anthropic", "claude-opus-4-7") in models
    assert ("anthropic", "claude-sonnet-4-6") in models
    assert ("anthropic", "claude-haiku-4-5") in models
    # All entries are anthropic for Phase 3.
    assert {p for p, _ in models} == {"anthropic"}


def test_rate_invariant_input_cheaper_than_output_for_every_model() -> None:
    """Across the Claude family the prompt rate is always lower than the
    completion rate (output is more expensive). This catches the typo
    where someone swaps input/output."""
    for provider, model in CostCalculator.supported_models():
        # Reach into _RATES via the calculator's table-driven contract.
        from olive_sdk.domain.services.cost_calculator import _RATES

        rate = _RATES[(provider, model)]
        assert isinstance(rate, Rate)
        assert rate.input_per_token < rate.output_per_token, (provider, model)
