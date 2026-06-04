"""ObjectStorage — outbound port for blob storage (PRD §6.7, §10.2).

Chat uploads (PDFs, audio clips) live in S3-compatible storage; the
adapter layer ships an aioboto3 implementation against MinIO/S3 plus
an in-memory implementation used by tests + local development.
"""

from __future__ import annotations

from typing import Protocol


class ObjectStorageError(Exception):
    """Raised when the storage backend rejects a put/get/delete."""


class ObjectNotFound(ObjectStorageError):
    """The requested key is not present in the storage backend."""


class ObjectStorage(Protocol):
    async def put(self, *, key: str, data: bytes, content_type: str) -> None:
        """Write ``data`` under ``key``. Overwrites if the key exists."""

    async def get(self, *, key: str) -> bytes:
        """Return the bytes stored under ``key`` or raise ObjectNotFound."""

    async def delete(self, *, key: str) -> None:
        """Remove ``key``. Idempotent — missing keys do not raise."""
