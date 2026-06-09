"""Tests for JwtVerifier (Phase 9.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from chat_service.infrastructure.auth.jwt_verifier import InvalidToken, JwtVerifier

SECRET = "super-secret-test-key-at-least-32-bytes-long"


def _token(claims: dict[str, object], *, secret: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, secret, algorithm=algorithm)


def test_empty_secret_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="non-empty secret"):
        JwtVerifier(secret="")


def test_valid_token_returns_sub_as_uuid() -> None:
    user_id = uuid4()
    verifier = JwtVerifier(secret=SECRET)
    assert verifier.verify(_token({"sub": str(user_id)})) == user_id


def test_wrong_signature_raises_invalid_token() -> None:
    verifier = JwtVerifier(secret=SECRET)
    with pytest.raises(InvalidToken):
        verifier.verify(
            _token({"sub": str(uuid4())}, secret="a-totally-different-secret-32-bytes-min")
        )


def test_expired_token_raises_invalid_token() -> None:
    verifier = JwtVerifier(secret=SECRET)
    expired = {
        "sub": str(uuid4()),
        "exp": int((datetime.now(tz=UTC) - timedelta(hours=1)).timestamp()),
    }
    with pytest.raises(InvalidToken):
        verifier.verify(_token(expired))


def test_missing_sub_raises_invalid_token() -> None:
    verifier = JwtVerifier(secret=SECRET)
    with pytest.raises(InvalidToken):
        verifier.verify(_token({"foo": "bar"}))


def test_non_uuid_sub_raises_invalid_token() -> None:
    verifier = JwtVerifier(secret=SECRET)
    with pytest.raises(InvalidToken, match="not a valid UUID"):
        verifier.verify(_token({"sub": "not-a-uuid"}))


def test_audience_is_enforced_when_configured() -> None:
    user_id = uuid4()
    verifier = JwtVerifier(secret=SECRET, audience="olive-api")

    good = verifier.verify(_token({"sub": str(user_id), "aud": "olive-api"}))
    assert good == user_id

    with pytest.raises(InvalidToken):
        verifier.verify(_token({"sub": str(user_id), "aud": "someone-else"}))


def test_issuer_is_enforced_when_configured() -> None:
    user_id = uuid4()
    verifier = JwtVerifier(secret=SECRET, issuer="olive-idp")

    good = verifier.verify(_token({"sub": str(user_id), "iss": "olive-idp"}))
    assert good == user_id

    with pytest.raises(InvalidToken):
        verifier.verify(_token({"sub": str(user_id), "iss": "evil-idp"}))
