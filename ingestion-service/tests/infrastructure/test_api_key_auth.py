"""Tests for ApiKeyAuthProvider rotation + config parsing (Phase 9.5)."""

from __future__ import annotations

from ingestion_service.config import IngestionSettings
from ingestion_service.infrastructure.auth.api_key_auth import ApiKeyAuthProvider

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


def test_single_key_is_accepted() -> None:
    provider = ApiKeyAuthProvider(allowed_keys=["key-a"])
    assert provider.is_valid("key-a") is True
    assert provider.is_valid("key-b") is False


def test_multiple_keys_are_all_accepted_during_rotation() -> None:
    """The whole point of rotation: old and new keys valid at once."""
    provider = ApiKeyAuthProvider(allowed_keys=["old-key", "new-key"])
    assert provider.is_valid("old-key") is True
    assert provider.is_valid("new-key") is True
    assert provider.is_valid("retired-key") is False


def test_empty_allow_list_rejects_everything() -> None:
    provider = ApiKeyAuthProvider(allowed_keys=[])
    assert provider.is_valid("anything") is False
    assert provider.is_valid("") is False


def test_blank_keys_are_filtered_out() -> None:
    provider = ApiKeyAuthProvider(allowed_keys=["", "  ".strip(), "real-key"])
    assert provider.is_valid("") is False
    assert provider.is_valid("real-key") is True


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def test_allowed_api_keys_merges_singular_and_plural() -> None:
    settings = IngestionSettings(
        ingestion_api_key="legacy-key",
        ingestion_api_keys="new-key-1, new-key-2",
    )
    assert settings.allowed_api_keys == frozenset({"legacy-key", "new-key-1", "new-key-2"})


def test_allowed_api_keys_strips_whitespace_and_blanks() -> None:
    settings = IngestionSettings(ingestion_api_keys="  a  , , b ,")
    assert settings.allowed_api_keys == frozenset({"a", "b"})


def test_allowed_api_keys_empty_when_unset() -> None:
    settings = IngestionSettings(ingestion_api_key="", ingestion_api_keys="")
    assert settings.allowed_api_keys == frozenset()


def test_provider_built_from_settings_supports_rotation() -> None:
    settings = IngestionSettings(ingestion_api_keys="old, new")
    provider = ApiKeyAuthProvider(allowed_keys=settings.allowed_api_keys)
    assert provider.is_valid("old") is True
    assert provider.is_valid("new") is True
