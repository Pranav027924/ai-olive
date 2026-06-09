"""JwtVerifier — HS256 bearer-token verification (PRD §9.4).

Verifies a signed JWT and returns the ``sub`` claim as the user's
UUID. Keeps verification rules (signature, expiry, optional
audience/issuer) in one place so the HTTP dependency stays thin.

Any failure — bad signature, expired token, missing/garbage ``sub`` —
raises :class:`InvalidToken`; the interface layer maps that to 401.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import jwt


class InvalidToken(Exception):
    """The presented bearer token failed verification."""


class JwtVerifier:
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str = "HS256",
        audience: str = "",
        issuer: str = "",
    ) -> None:
        if not secret:
            raise ValueError("JwtVerifier requires a non-empty secret")
        self._secret = secret
        self._algorithm = algorithm
        self._audience = audience or None
        self._issuer = issuer or None

    def verify(self, token: str) -> UUID:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options=cast("Any", {"require": ["sub"]}),
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidToken(str(exc)) from exc

        sub = claims.get("sub")
        if not isinstance(sub, str):
            raise InvalidToken("token 'sub' claim is missing or not a string")
        try:
            return UUID(sub)
        except ValueError as exc:
            raise InvalidToken(f"token 'sub' is not a valid UUID: {sub!r}") from exc
