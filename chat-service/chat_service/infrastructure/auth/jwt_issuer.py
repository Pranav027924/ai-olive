"""JwtIssuer — mints HS256 access tokens (PRD §9.4).

The counterpart to :class:`JwtVerifier`: signs a token whose ``sub`` is
the user's id, with an expiry. The same ``JWT_SECRET`` verifies it on
the protected endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt


class JwtIssuer:
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str = "HS256",
        ttl_minutes: int = 60 * 24 * 7,
        audience: str = "",
        issuer: str = "",
    ) -> None:
        if not secret:
            raise ValueError("JwtIssuer requires a non-empty secret")
        self._secret = secret
        self._algorithm = algorithm
        self._ttl = timedelta(minutes=ttl_minutes)
        self._audience = audience
        self._issuer = issuer

    def issue(self, user_id: UUID) -> str:
        now = datetime.now(tz=UTC)
        claims: dict[str, object] = {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        if self._audience:
            claims["aud"] = self._audience
        if self._issuer:
            claims["iss"] = self._issuer
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)
