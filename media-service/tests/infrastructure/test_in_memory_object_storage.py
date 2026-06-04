"""Tests for InMemoryObjectStorage (Phase 6.7)."""

from __future__ import annotations

import pytest
from media_service.application.ports.object_storage import ObjectNotFound
from media_service.infrastructure.storage.in_memory_object_storage import (
    InMemoryObjectStorage,
)


async def test_put_then_get_roundtrips_bytes() -> None:
    storage = InMemoryObjectStorage()

    await storage.put(key="a/b.pdf", data=b"hello", content_type="application/pdf")

    assert await storage.get(key="a/b.pdf") == b"hello"
    assert storage.content_type("a/b.pdf") == "application/pdf"


async def test_put_overwrites_existing_key() -> None:
    storage = InMemoryObjectStorage()

    await storage.put(key="k", data=b"one", content_type="text/plain")
    await storage.put(key="k", data=b"two", content_type="text/plain")

    assert await storage.get(key="k") == b"two"


async def test_get_missing_key_raises_object_not_found() -> None:
    storage = InMemoryObjectStorage()

    with pytest.raises(ObjectNotFound):
        await storage.get(key="nope")


async def test_delete_is_idempotent() -> None:
    storage = InMemoryObjectStorage()
    await storage.put(key="k", data=b"x", content_type="text/plain")

    await storage.delete(key="k")
    await storage.delete(key="k")  # again, no raise

    with pytest.raises(ObjectNotFound):
        await storage.get(key="k")


async def test_keys_lists_stored_objects() -> None:
    storage = InMemoryObjectStorage()

    await storage.put(key="a", data=b"1", content_type="text/plain")
    await storage.put(key="b", data=b"2", content_type="text/plain")

    assert set(storage.keys()) == {"a", "b"}
