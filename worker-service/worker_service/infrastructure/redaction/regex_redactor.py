"""Regex-based redactors (PRD §6.4).

Each factory returns a small :class:`Redactor` matching the
``RedactionPipeline`` Protocol. Plug them into ``RedactionPipeline``
in priority order.

Patterns enabled by default:
    email          local@host.tld           → ``<email>``
    us_phone       (xxx) xxx-xxxx etc.      → ``<phone>``
    credit_card    13-19 digits, Luhn-valid → ``<cc>``
    api_key        sk-…, sk_ant-…, gho_…    → ``<api-key>``

The default pipeline is :func:`default_pipeline` — wire it into the
``ProcessLogEvent`` use case unless a particular environment needs
different masks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from worker_service.domain.services.redaction_pipeline import (
    RedactionPipeline,
)

EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)

US_PHONE_PATTERN = re.compile(
    r"(?<!\d)"  # left boundary: no digit just before
    r"(?:\+?1[\s.-]?)?"  # optional country code
    r"(?:\(\d{3}\)|\d{3})"  # area code (with or without parens)
    r"[\s.-]?\d{3}[\s.-]?\d{4}"  # 3 + 4
    r"(?!\d)",  # right boundary: no digit just after
)

# 13-19 digits with optional separators between them.
CC_PATTERN = re.compile(
    r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)",
)

# Common public-prefix API keys: OpenAI sk-, Anthropic sk-ant-, GitHub gho_,
# generic Bearer tokens we obviously shouldn't log. We require at least 20
# trailing chars so we don't redact ordinary words.
API_KEY_PATTERN = re.compile(
    r"\b("
    r"sk-ant-[A-Za-z0-9_\-]{20,}"
    r"|sk-[A-Za-z0-9_\-]{20,}"
    r"|gho_[A-Za-z0-9_\-]{20,}"
    r"|ghp_[A-Za-z0-9_\-]{20,}"
    r"|github_pat_[A-Za-z0-9_\-]{20,}"
    r")\b",
)


@dataclass(frozen=True, slots=True)
class _SimpleRedactor:
    pattern: re.Pattern[str]
    replacement: str

    def redact(self, text: str) -> str:
        return self.pattern.sub(self.replacement, text)


@dataclass(frozen=True, slots=True)
class _LuhnRedactor:
    """Only replaces digit runs that pass the Luhn checksum."""

    pattern: re.Pattern[str]
    replacement: str

    def redact(self, text: str) -> str:
        return self.pattern.sub(self._maybe, text)

    def _maybe(self, match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        return self.replacement if _luhn_valid(digits) else match.group()


def _luhn_valid(digits: str) -> bool:
    if not digits:
        return False
    total = 0
    parity = (len(digits) - 2) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def email_redactor(replacement: str = "<email>") -> _SimpleRedactor:
    return _SimpleRedactor(EMAIL_PATTERN, replacement)


def us_phone_redactor(replacement: str = "<phone>") -> _SimpleRedactor:
    return _SimpleRedactor(US_PHONE_PATTERN, replacement)


def credit_card_redactor(replacement: str = "<cc>") -> _LuhnRedactor:
    return _LuhnRedactor(CC_PATTERN, replacement)


def api_key_redactor(replacement: str = "<api-key>") -> _SimpleRedactor:
    return _SimpleRedactor(API_KEY_PATTERN, replacement)


def default_pipeline() -> RedactionPipeline:
    return RedactionPipeline(
        redactors=(
            api_key_redactor(),  # cheap; catches "sk-..." before CC regex sees the digits
            email_redactor(),
            credit_card_redactor(),
            us_phone_redactor(),
        ),
    )
