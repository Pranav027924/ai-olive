"""InMemoryObjectStorage — fast, dependency-free ObjectStorage.

Used by chat-service unit tests and by local dev when MinIO isn't
running. Not threadsafe — fine for asyncio's single-loop model.
"""

from __future__ import annotations

from dataclasses import dataclass

from media_service.application.ports.object_storage import ObjectNotFound, ObjectStorage


@dataclass(frozen=True, slots=True)
class StoredObject:
    data: bytes
    content_type: str


class InMemoryObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self._objects: dict[str, StoredObject] = {}

    async def put(self, *, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = StoredObject(data=data, content_type=content_type)

    async def get(self, *, key: str) -> bytes:
        try:
            return self._objects[key].data
        except KeyError as exc:
            raise ObjectNotFound(key) from exc

    async def delete(self, *, key: str) -> None:
        self._objects.pop(key, None)

    def content_type(self, key: str) -> str | None:
        obj = self._objects.get(key)
        return obj.content_type if obj else None

    def keys(self) -> tuple[str, ...]:
        return tuple(self._objects.keys())
