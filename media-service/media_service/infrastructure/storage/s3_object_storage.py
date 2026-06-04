"""S3ObjectStorage — aioboto3 ObjectStorage against S3 / MinIO (PRD §6.7).

aioboto3 builds clients via an async context manager; we re-open one
per call to keep the adapter stateless and safe to share across the
event loop. The session itself is cheap to keep around.
"""

from __future__ import annotations

from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from media_service.application.ports.object_storage import (
    ObjectNotFound,
    ObjectStorage,
    ObjectStorageError,
)


class S3ObjectStorage(ObjectStorage):
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region_name: str = "us-east-1",
        session: aioboto3.Session | None = None,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region_name
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._session = session or aioboto3.Session()

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
        )

    async def put(self, *, key: str, data: bytes, content_type: str) -> None:
        async with self._client() as s3:
            await s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    async def get(self, *, key: str) -> bytes:
        async with self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code in {"NoSuchKey", "404"}:
                    raise ObjectNotFound(key) from exc
                raise ObjectStorageError(f"S3 get_object failed: {code}") from exc
            async with response["Body"] as stream:
                payload: bytes = await stream.read()
                return payload

    async def delete(self, *, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
