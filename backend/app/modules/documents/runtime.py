"""Validated storage and scanner composition for employee documents."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.documents.scanning import (
    ClamAVMalwareScanner,
    LocalCleanMalwareScanner,
    MalwareScanner,
)
from app.platform.storage import (
    ObjectStorage,
    S3ObjectStorage,
    UnavailableObjectStorage,
)

DOCUMENT_RUNTIME_STATE_KEY = "document_runtime"


@dataclass(slots=True)
class DocumentRuntime:
    storage: ObjectStorage
    scanner: MalwareScanner

    async def initialize(self) -> None:
        await self.storage.initialize()

    async def close(self) -> None:
        await self.storage.close()


def create_document_runtime(settings: Settings) -> DocumentRuntime:
    _validate_configuration(settings)
    if settings.document_storage_backend == "s3":
        access_key = settings.s3_access_key_id
        secret_key = settings.s3_secret_access_key
        internal_endpoint = settings.s3_internal_endpoint_url
        if access_key is None or secret_key is None or internal_endpoint is None:
            raise ValueError("S3 employee document storage credentials and endpoint are required")
        storage: ObjectStorage = S3ObjectStorage(
            internal_endpoint_url=internal_endpoint,
            presign_endpoint_url=settings.s3_presign_endpoint_url or internal_endpoint,
            region=settings.s3_region,
            bucket=settings.s3_bucket,
            access_key_id=access_key.get_secret_value(),
            secret_access_key=secret_key.get_secret_value(),
            session_token=(
                settings.s3_session_token.get_secret_value()
                if settings.s3_session_token is not None
                else None
            ),
            addressing_style=settings.s3_addressing_style,
            connect_timeout_seconds=settings.s3_connect_timeout_seconds,
            read_timeout_seconds=settings.s3_read_timeout_seconds,
            create_bucket=settings.s3_create_bucket,
        )
    else:
        storage = UnavailableObjectStorage()

    if settings.document_scanner_backend == "clamav":
        if settings.clamav_host is None:
            raise ValueError("ClamAV host is required when the ClamAV scanner is selected")
        scanner: MalwareScanner = ClamAVMalwareScanner(
            host=settings.clamav_host,
            port=settings.clamav_port,
            connect_timeout_seconds=settings.clamav_connect_timeout_seconds,
            scan_timeout_seconds=settings.clamav_scan_timeout_seconds,
        )
    else:
        scanner = LocalCleanMalwareScanner()
    return DocumentRuntime(storage=storage, scanner=scanner)


def _validate_configuration(settings: Settings) -> None:
    protected_environment = settings.environment in {"staging", "prod"}
    if protected_environment and settings.document_storage_backend != "s3":
        raise ValueError("Staging and production require S3 employee document storage")
    if protected_environment and settings.document_scanner_backend != "clamav":
        raise ValueError("Staging and production require the ClamAV employee document scanner")
    if settings.document_storage_backend == "s3":
        missing = [
            name
            for name, value in (
                ("IK_S3_INTERNAL_ENDPOINT_URL", settings.s3_internal_endpoint_url),
                ("IK_S3_ACCESS_KEY_ID", settings.s3_access_key_id),
                ("IK_S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key),
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"S3 employee document configuration is missing {', '.join(missing)}")
    if settings.document_scanner_backend == "clamav" and not settings.clamav_host:
        raise ValueError("ClamAV employee document configuration is missing IK_CLAMAV_HOST")


__all__ = ["DOCUMENT_RUNTIME_STATE_KEY", "DocumentRuntime", "create_document_runtime"]
