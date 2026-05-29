"""CostCalculator — provider+model → USD cost (PRD §6.4 / §10.1).

Intentional duplicate of the SDK's ``olive_sdk.domain.services.
cost_calculator`` (PRD §6.4). The worker's copy is canonical for the
``cost_usd`` column persisted to Postgres / ClickHouse — a stale SDK
release can't poison the analytics value because the worker recomputes
from the raw token counts every time.

The table is structurally identical to the SDK's; this duplication is
deliberate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Rate:
    input_per_token: Decimal
    output_per_token: Decimal


def _per_million(*, input_usd_per_m: str, output_usd_per_m: str) -> Rate:
    return Rate(
        input_per_token=Decimal(input_usd_per_m) / Decimal("1000000"),
        output_per_token=Decimal(output_usd_per_m) / Decimal("1000000"),
    )


_RATES: dict[tuple[str, str], Rate] = {
    ("anthropic", "claude-opus-4-7"): _per_million(input_usd_per_m="15", output_usd_per_m="75"),
    ("anthropic", "claude-opus-4-6"): _per_million(input_usd_per_m="15", output_usd_per_m="75"),
    ("anthropic", "claude-opus-4-5"): _per_million(input_usd_per_m="15", output_usd_per_m="75"),
    ("anthropic", "claude-sonnet-4-6"): _per_million(input_usd_per_m="3", output_usd_per_m="15"),
    ("anthropic", "claude-sonnet-4-5"): _per_million(input_usd_per_m="3", output_usd_per_m="15"),
    ("anthropic", "claude-haiku-4-5"): _per_million(input_usd_per_m="0.80", output_usd_per_m="4"),
}


class CostCalculator:
    def estimate(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> Decimal | None:
        rate = _RATES.get((provider, model))
        if rate is None:
            return None
        prompt = Decimal(prompt_tokens or 0)
        completion = Decimal(completion_tokens or 0)
        return rate.input_per_token * prompt + rate.output_per_token * completion

    @staticmethod
    def supported_models() -> list[tuple[str, str]]:
        return list(_RATES.keys())
