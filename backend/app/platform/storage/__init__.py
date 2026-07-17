"""Private object-storage contracts and S3-compatible production adapter."""

from app.platform.storage.contracts import (
    DownloadedObject,
    ObjectAlreadyExistsError,
    ObjectHead,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    ObjectStorageUnavailableError,
    PresignedRequest,
    UploadedObject,
)
from app.platform.storage.s3 import S3ObjectStorage
from app.platform.storage.unavailable import UnavailableObjectStorage

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
    "S3ObjectStorage",
    "UnavailableObjectStorage",
]
