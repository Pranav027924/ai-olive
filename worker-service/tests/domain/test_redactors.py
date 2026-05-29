"""Exhaustive tests for the regex redactors (Phase 5.3)."""

from __future__ import annotations

import pytest
from worker_service.domain.services.redaction_pipeline import RedactionPipeline
from worker_service.infrastructure.redaction.regex_redactor import (
    api_key_redactor,
    credit_card_redactor,
    default_pipeline,
    email_redactor,
    us_phone_redactor,
)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hi alice@example.com bye", "hi <email> bye"),
        ("a.b+c@sub.example.co.uk works", "<email> works"),
        ("multi a@x.io and b@y.io", "multi <email> and <email>"),
        ("no @ here", "no @ here"),
        (
            "short TLDs like x@a.b are NOT matched (TLD <2)",
            "short TLDs like x@a.b are NOT matched (TLD <2)",
        ),
    ],
)
def test_email_redactor(text: str, expected: str) -> None:
    assert email_redactor().redact(text) == expected


# ---------------------------------------------------------------------------
# US phone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("call (415) 555-1234", "call <phone>"),
        ("ph: 415-555-1234", "ph: <phone>"),
        ("415.555.1234 ok", "<phone> ok"),
        ("+1 415 555 1234 yes", "<phone> yes"),
        ("4155551234 too", "<phone> too"),
        ("no phone here", "no phone here"),
        ("longer 12345678901234 keep", "longer 12345678901234 keep"),  # too long
    ],
)
def test_us_phone_redactor(text: str, expected: str) -> None:
    assert us_phone_redactor().redact(text) == expected


# ---------------------------------------------------------------------------
# Credit card (Luhn-validated)
# ---------------------------------------------------------------------------


# Real Luhn-valid test numbers — these are the standard public examples
# (Visa, Mastercard, Amex test PANs).
VALID_CC = [
    "4242 4242 4242 4242",
    "4111111111111111",
    "5555-5555-5555-4444",
    "378282246310005",  # Amex 15-digit
]

INVALID_CC = [
    "1234 5678 9012 3456",  # fails Luhn
    "1111 1111 1111 1111",  # fails Luhn
    "4242 4242 4242 4243",  # off by one from the valid 4242… run
]


@pytest.mark.parametrize("text", VALID_CC)
def test_luhn_valid_cards_are_redacted(text: str) -> None:
    out = credit_card_redactor().redact(f"pay {text} now")
    assert out == "pay <cc> now"


@pytest.mark.parametrize("text", INVALID_CC)
def test_luhn_invalid_digit_runs_are_left_alone(text: str) -> None:
    """Looks like a CC but fails Luhn — must not be redacted (avoids false
    positives on order numbers, etc.)."""
    out = credit_card_redactor().redact(f"order {text} processed")
    assert out == f"order {text} processed"


def test_credit_card_handles_inline_text() -> None:
    text = "received 4242 4242 4242 4242 charged"
    assert credit_card_redactor().redact(text) == "received <cc> charged"


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "sk-1234567890abcdefghijABCD",
        "sk-ant-api03-abcdefghijklmnop0123456789",
        "gho_abcdefghij1234567890ABCD",
        "ghp_1234567890abcdefghijklmn",
        "github_pat_11ABCDEFG0_abcdefghijabcdefghijabcdefghijabcdefghij",
    ],
)
def test_api_key_patterns(key: str) -> None:
    out = api_key_redactor().redact(f"key={key} here")
    assert out == "key=<api-key> here"


def test_api_key_short_string_is_not_a_match() -> None:
    # "sk-" by itself is way too short to be a real token — should not be
    # redacted.
    assert api_key_redactor().redact("just sk- alone") == "just sk- alone"


def test_api_key_does_not_redact_ordinary_words() -> None:
    assert api_key_redactor().redact("this is a normal sentence") == "this is a normal sentence"


# ---------------------------------------------------------------------------
# Pipeline ordering + composition
# ---------------------------------------------------------------------------


def test_default_pipeline_redacts_all_four_in_one_pass() -> None:
    text = (
        "Email bob@example.com or call (555) 123-4567, "
        "card 4242 4242 4242 4242, token sk-1234567890abcdefghijABCD"
    )
    out = default_pipeline().redact(text)
    assert "bob@example.com" not in out
    assert "<email>" in out
    assert "(555) 123-4567" not in out
    assert "<phone>" in out
    assert "4242" not in out
    assert "<cc>" in out
    assert "sk-1234567890abcdefghijABCD" not in out
    assert "<api-key>" in out


def test_redaction_pipeline_with_no_redactors_returns_input_unchanged() -> None:
    assert RedactionPipeline().redact("anything goes 42") == "anything goes 42"


def test_pipeline_order_matters_when_redactors_compete() -> None:
    """Putting the API-key redactor before CC means a long token starting
    with sk- whose digit-tail looks like Luhn-valid digits still becomes
    <api-key>, not <cc>."""
    text = "token sk-4242424242424242abcdef has both shapes"
    out = default_pipeline().redact(text)
    assert "<api-key>" in out
    assert "<cc>" not in out
