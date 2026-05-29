"""ApiKeyAuthProvider — single-key inter-service auth (PRD §9.5).

Single shared secret for now; rotation lands in Phase 9.5. The
provider is constructed once per process from settings and exposed
via dependencies.py.
"""

from __future__ import annotations

from ingestion_service.application.ports.auth_provider import AuthProvider


class ApiKeyAuthProvider(AuthProvider):
    def __init__(self, *, expected_key: str) -> None:
        self._expected_key = expected_key

    def is_valid(self, api_key: str) -> bool:
        # Empty configured key is always rejected so a misconfigured
        # service never accidentally allows traffic.
        if not self._expected_key:
            return False
        return api_key == self._expected_key
