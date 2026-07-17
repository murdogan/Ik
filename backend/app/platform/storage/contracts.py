"""Small async object-storage contracts used by employee documents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class ObjectStorageError(RuntimeError):
    """Provider failure whose raw details must not cross the storage boundary."""


class ObjectNotFoundError(ObjectStorageError):
    pass


class ObjectAlreadyExistsError(ObjectStorageError):
    pass


class ObjectStorageUnavailableError(ObjectStorageError):
    pass


@dataclass(frozen=True, slots=True)
class ObjectHead:
    key: str
    size_bytes: int
    content_type: str
    metadata: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class PresignedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class DownloadedObject:
    size_bytes: int
    sha256: str
    magic_prefix: bytes


@dataclass(frozen=True, slots=True)
class UploadedObject:
    size_bytes: int
    sha256: str


class ObjectStorage(Protocol):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def presign_upload(
        self,
        *,
        key: str,
        content_type: str,
        content_length: int,
        metadata: Mapping[str, str],
        ttl_seconds: int,
    ) -> PresignedRequest: ...

    async def head(self, key: str) -> ObjectHead: ...

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        maximum_bytes: int,
    ) -> DownloadedObject: ...

    async def upload_from_path(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        metadata: Mapping[str, str],
        maximum_bytes: int,
    ) -> UploadedObject: ...

    async def copy_if_absent(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def presign_download(
        self,
        *,
        key: str,
        download_name: str,
        ttl_seconds: int,
    ) -> PresignedRequest: ...


__all__ = [
    "DownloadedObject",
    "ObjectAlreadyExistsError",
    "ObjectHead",
    "ObjectNotFoundError",
    "ObjectStorage",
    "ObjectStorageError",
    "ObjectStorageUnavailableError",
    "PresignedRequest",
    "UploadedObject",
]
