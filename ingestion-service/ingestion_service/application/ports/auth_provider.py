"""AuthProvider — outbound port for inter-service auth (PRD §6.3, §9.5).

Phase 4.6 ships :class:`ApiKeyAuthProvider`. Real OIDC integration
is Phase 9.4.
"""

from __future__ import annotations

from typing import Protocol


class AuthProvider(Protocol):
    def is_valid(self, api_key: str) -> bool:
        """Return True iff ``api_key`` is currently authorised to call the service."""
