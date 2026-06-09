"""ApiKeyAuthProvider — multi-key inter-service auth (PRD §9.5).

Holds an allow-list of currently-valid API keys so keys can be
rotated with zero downtime: add the new key to the set, roll clients
onto it, then remove the old key. Comparison is constant-time
(``hmac.compare_digest``) against every allowed key so a presented
key's validity can't be inferred from response timing.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable

from ingestion_service.application.ports.auth_provider import AuthProvider


class ApiKeyAuthProvider(AuthProvider):
    def __init__(self, *, allowed_keys: Iterable[str]) -> None:
        self._allowed_keys = frozenset(k for k in allowed_keys if k)

    def is_valid(self, api_key: str) -> bool:
        if not api_key or not self._allowed_keys:
            # No keys configured → reject everything so a misconfigured
            # service never accidentally allows traffic.
            return False
        # Compare against every key (no early return) to keep timing flat.
        valid = False
        for allowed in self._allowed_keys:
            if hmac.compare_digest(api_key, allowed):
                valid = True
        return valid
