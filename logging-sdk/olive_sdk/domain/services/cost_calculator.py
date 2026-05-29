"""CostCalculator — provider+model → USD cost (PRD §10.1, Phase 3.2).

Table-driven strategy: each entry in ``_RATES`` maps a
``(provider, model)`` pair to an :class:`Rate` of input and output
USD-per-token rates. The calculator multiplies by the prompt /
completion token counts captured by the SDK and returns a Decimal.

Unknown ``(provider, model)`` pairs return ``None`` rather than
guessing — silently mispriced rows would be worse than a missing
``cost_usd`` on the analytics side.

Rates are kept in this module deliberately:
- self-contained (no I/O, no external config)
- type-safe (mypy --strict catches typos)
- easy to update via a one-line PR when prices change

The worker service also has its own CostCalculator (PRD §6.4); the
two are intentionally duplicated so a stale SDK release can't poison
the canonical cost stored in Postgres / ClickHouse.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Rate:
    """USD rate per single input/output token (i.e. price per million / 1_000_000)."""

    input_per_token: Decimal
    output_per_token: Decimal


def _per_million(*, input_usd_per_m: str, output_usd_per_m: str) -> Rate:
    return Rate(
        input_per_token=Decimal(input_usd_per_m) / Decimal("1000000"),
        output_per_token=Decimal(output_usd_per_m) / Decimal("1000000"),
    )


# (provider, model) → Rate. Prices are rough public list as of 2026-Q2 — they
# update via PR when Anthropic/OpenAI/etc. announce changes.
_RATES: dict[tuple[str, str], Rate] = {
    ("anthropic", "claude-opus-4-7"): _per_million(input_usd_per_m="15", output_usd_per_m="75"),
    ("anthropic", "claude-opus-4-6"): _per_million(input_usd_per_m="15", output_usd_per_m="75"),
    ("anthropic", "claude-opus-4-5"): _per_million(input_usd_per_m="15", output_usd_per_m="75"),
    ("anthropic", "claude-sonnet-4-6"): _per_million(input_usd_per_m="3", output_usd_per_m="15"),
    ("anthropic", "claude-sonnet-4-5"): _per_million(input_usd_per_m="3", output_usd_per_m="15"),
    ("anthropic", "claude-haiku-4-5"): _per_million(input_usd_per_m="0.80", output_usd_per_m="4"),
}


class CostCalculator:
    """Pure domain service. No I/O. Equality is by-identity (no fields)."""

    def estimate(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> Decimal | None:
        """Return the USD cost or ``None`` for unknown (provider, model).

        ``None`` token counts are treated as ``0`` so the same calculator
        can be called for error rows where the provider returned no
        usage block.
        """
        rate = _RATES.get((provider, model))
        if rate is None:
            return None
        prompt = Decimal(prompt_tokens or 0)
        completion = Decimal(completion_tokens or 0)
        return rate.input_per_token * prompt + rate.output_per_token * completion

    @staticmethod
    def supported_models() -> list[tuple[str, str]]:
        """Return all known (provider, model) pairs. Useful for tests."""
        return list(_RATES.keys())
