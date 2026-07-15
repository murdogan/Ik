"""Fail-closed local adapter used only when documents are explicitly disabled."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.platform.storage.contracts import (
    DownloadedObject,
    ObjectHead,
    ObjectStorageUnavailableError,
    PresignedRequest,
)


class UnavailableObjectStorage:
    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def presign_upload(
        self,
        *,
        key: str,
        content_type: str,
        content_length: int,
        metadata: Mapping[str, str],
        ttl_seconds: int,
    ) -> PresignedRequest:
        raise ObjectStorageUnavailableError("Employee document storage is not configured")

    async def head(self, key: str) -> ObjectHead:
        raise ObjectStorageUnavailableError("Employee document storage is not configured")

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        maximum_bytes: int,
    ) -> DownloadedObject:
        raise ObjectStorageUnavailableError("Employee document storage is not configured")

    async def copy_if_absent(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> None:
        raise ObjectStorageUnavailableError("Employee document storage is not configured")

    async def delete(self, key: str) -> None:
        raise ObjectStorageUnavailableError("Employee document storage is not configured")

    async def presign_download(
        self,
        *,
        key: str,
        download_name: str,
        ttl_seconds: int,
    ) -> PresignedRequest:
        raise ObjectStorageUnavailableError("Employee document storage is not configured")


__all__ = ["UnavailableObjectStorage"]
