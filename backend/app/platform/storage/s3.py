"""S3-compatible private-object adapter with externally valid presigning."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.platform.storage.contracts import (
    DownloadedObject,
    ObjectAlreadyExistsError,
    ObjectHead,
    ObjectNotFoundError,
    ObjectStorageError,
    PresignedRequest,
)


class S3ObjectStorage:
    def __init__(
        self,
        *,
        internal_endpoint_url: str,
        presign_endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        session_token: str | None,
        addressing_style: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        create_bucket: bool,
    ) -> None:
        config = Config(
            signature_version="s3v4",
            connect_timeout=connect_timeout_seconds,
            read_timeout=read_timeout_seconds,
            retries={"max_attempts": 3, "mode": "standard"},
            s3={"addressing_style": addressing_style},
        )
        credentials: dict[str, object] = {
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
        }
        if session_token is not None:
            credentials["aws_session_token"] = session_token
        self._client: BaseClient = boto3.client(
            "s3",
            endpoint_url=internal_endpoint_url,
            region_name=region,
            config=config,
            **credentials,
        )
        self._presign_client: BaseClient = boto3.client(
            "s3",
            endpoint_url=presign_endpoint_url,
            region_name=region,
            config=config,
            **credentials,
        )
        self._bucket = bucket
        self._region = region
        self._create_bucket = create_bucket

    async def initialize(self) -> None:
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
            return
        except ClientError as exc:
            status = _http_status(exc)
            if status not in {404, 400} or not self._create_bucket:
                raise ObjectStorageError("Object storage bucket is unavailable") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError("Object storage bucket is unavailable") from exc

        parameters: dict[str, Any] = {"Bucket": self._bucket}
        if self._region != "us-east-1":
            parameters["CreateBucketConfiguration"] = {
                "LocationConstraint": self._region,
            }
        try:
            await asyncio.to_thread(self._client.create_bucket, **parameters)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError("Object storage bucket could not be initialized") from exc

    async def close(self) -> None:
        await asyncio.gather(
            asyncio.to_thread(self._client.close),
            asyncio.to_thread(self._presign_client.close),
        )

    async def presign_upload(
        self,
        *,
        key: str,
        content_type: str,
        content_length: int,
        metadata: Mapping[str, str],
        ttl_seconds: int,
    ) -> PresignedRequest:
        _validate_key(key)
        parameters = {
            "Bucket": self._bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": content_length,
            "Metadata": dict(metadata),
            "IfNoneMatch": "*",
        }
        try:
            url = self._presign_client.generate_presigned_url(
                "put_object",
                Params=parameters,
                ExpiresIn=ttl_seconds,
                HttpMethod="PUT",
            )
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise ObjectStorageError("Upload authorization could not be created") from exc
        headers = {
            "Content-Type": content_type,
            "If-None-Match": "*",
            **{f"x-amz-meta-{name}": value for name, value in metadata.items()},
        }
        return PresignedRequest(
            method="PUT",
            url=url,
            headers=headers,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )

    async def head(self, key: str) -> ObjectHead:
        _validate_key(key)
        try:
            response = await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=key,
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError("Object was not found") from exc
            raise ObjectStorageError("Object metadata could not be read") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError("Object metadata could not be read") from exc
        return ObjectHead(
            key=key,
            size_bytes=int(response.get("ContentLength", -1)),
            content_type=str(response.get("ContentType", "")),
            metadata={
                str(name).lower(): str(value)
                for name, value in response.get("Metadata", {}).items()
            },
        )

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        maximum_bytes: int,
    ) -> DownloadedObject:
        _validate_key(key)
        try:
            return await asyncio.to_thread(
                self._download_to_path_sync,
                key,
                destination,
                maximum_bytes,
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError("Object was not found") from exc
            raise ObjectStorageError("Object could not be read") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError("Object could not be read") from exc

    def _download_to_path_sync(
        self,
        key: str,
        destination: Path,
        maximum_bytes: int,
    ) -> DownloadedObject:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        digest = hashlib.sha256()
        size_bytes = 0
        magic_prefix = bytearray()
        try:
            with destination.open("xb") as file_handle:
                while True:
                    chunk = body.read(128 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > maximum_bytes:
                        raise ObjectStorageError("Object exceeds the bounded download size")
                    if len(magic_prefix) < 32:
                        magic_prefix.extend(chunk[: 32 - len(magic_prefix)])
                    digest.update(chunk)
                    file_handle.write(chunk)
        finally:
            body.close()
        return DownloadedObject(
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            magic_prefix=bytes(magic_prefix),
        )

    async def copy_if_absent(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> None:
        _validate_key(source_key)
        _validate_key(destination_key)
        try:
            await self.head(destination_key)
        except ObjectNotFoundError:
            pass
        else:
            raise ObjectAlreadyExistsError("Destination object already exists")
        try:
            await asyncio.to_thread(
                self._client.copy_object,
                Bucket=self._bucket,
                Key=destination_key,
                CopySource={"Bucket": self._bucket, "Key": source_key},
                ContentType=content_type,
                Metadata=dict(metadata),
                MetadataDirective="REPLACE",
            )
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError("Source object was not found") from exc
            raise ObjectStorageError("Object could not be finalized") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError("Object could not be finalized") from exc

    async def delete(self, key: str) -> None:
        _validate_key(key)
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=key,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError("Object could not be removed") from exc

    async def presign_download(
        self,
        *,
        key: str,
        download_name: str,
        ttl_seconds: int,
    ) -> PresignedRequest:
        _validate_key(key)
        if not download_name or any(character in download_name for character in {'"', "\r", "\n"}):
            raise ValueError("Download name is unsafe")
        try:
            url = self._presign_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{download_name}"',
                },
                ExpiresIn=ttl_seconds,
                HttpMethod="GET",
            )
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise ObjectStorageError("Download authorization could not be created") from exc
        return PresignedRequest(
            method="GET",
            url=url,
            headers={},
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )


def _validate_key(key: str) -> None:
    if not key or key.startswith("/") or ".." in key.split("/") or "\\" in key:
        raise ValueError("Object key is unsafe")
    if any(ord(character) < 32 for character in key):
        raise ValueError("Object key is unsafe")


def _http_status(exc: ClientError) -> int | None:
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return status if isinstance(status, int) else None


def _is_not_found(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return _http_status(exc) == 404 or code in {"404", "NoSuchKey", "NotFound"}


__all__ = ["S3ObjectStorage"]
