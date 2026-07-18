#!/usr/bin/env python3
"""Fail-closed PostgreSQL and object-storage recovery operations."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, NoReturn

BACKUP_FORMAT = "postgresql_custom"
BACKUP_SCHEMA_VERSION = 1
DATABASE_DUMP_NAME = "database.dump"
MANIFEST_NAME = "manifest.json"
CHECKSUMS_NAME = "SHA256SUMS"
OBJECTS_DIRECTORY_NAME = "objects"
DEFAULT_TIMEOUT_SECONDS = 1_800
MAX_TIMEOUT_SECONDS = 86_400
MAX_JSON_BYTES = 1_048_576
MAX_CHECKSUM_BYTES = 67_108_864
MAX_RELEASE_MANIFEST_BYTES = 65_536
MAX_OBJECTS = 1_000_000
OBJECT_DIGEST_DOMAIN = b"IK_RECOVERY_OBJECTS_V1\x00"

CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")
HEX_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
REVISION_PATTERN = re.compile(r"[0-9a-z_]+")
DATABASE_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_$.-]{0,62}")
BACKUP_NAME_PATTERN = re.compile(r"backup-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}")
PROOF_DATABASE_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,62}_restore_proof")
ALIAS_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")
CHANGE_TICKET_PATTERN = re.compile(r"[A-Z][A-Z0-9]{1,15}-[1-9][0-9]{0,11}")
APP_VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
UTC_TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

KNOWN_ENVIRONMENTS = frozenset({"local", "dev", "test", "staging", "prod"})
PROTECTED_DATABASE_NAMES = frozenset({"postgres", "template0", "template1"})
IDENTITY_QUERY_OPTIONS = frozenset(
    {
        "database",
        "dbname",
        "host",
        "hostaddr",
        "passfile",
        "password",
        "port",
        "service",
        "servicefile",
        "target_session_attrs",
        "user",
    }
)
TLS_PATH_OPTIONS = {
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcrl": "PGSSLCRL",
    "sslcrldir": "PGSSLCRLDIR",
}


class RecoveryError(Exception):
    """An intentionally generic, machine-readable recovery failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise RecoveryError("INVALID_ARGUMENT")


@dataclasses.dataclass(frozen=True, slots=True)
class PostgresConnection:
    host: str
    port: int
    username: str
    password: str = dataclasses.field(repr=False)
    database: str
    option_environment: tuple[tuple[str, str], ...]

    @property
    def server_identity(self) -> tuple[str, int]:
        return (self.host.casefold(), self.port)


@dataclasses.dataclass(frozen=True, slots=True)
class ObjectEntry:
    relative_path: str
    encoded_path: str
    sha256: str
    size_bytes: int


@dataclasses.dataclass(frozen=True, slots=True)
class ObjectAggregate:
    aggregate_sha256: str
    object_count: int
    total_bytes: int
    entries: tuple[ObjectEntry, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class VerifiedBackup:
    backup_directory: Path
    manifest: dict[str, Any]


def _raise(reason_code: str) -> NoReturn:
    raise RecoveryError(reason_code)


def _contains_control(value: str) -> bool:
    return CONTROL_PATTERN.search(value) is not None


def _validate_percent_escapes(value: str) -> None:
    index = 0
    while index < len(value):
        if value[index] == "%":
            if index + 2 >= len(value) or not all(
                character in "0123456789abcdefABCDEF" for character in value[index + 1 : index + 3]
            ):
                _raise("INVALID_DATABASE_CONFIG")
            index += 3
            continue
        index += 1


def _strict_unquote(value: str) -> str:
    _validate_percent_escapes(value)
    try:
        decoded = urllib.parse.unquote_to_bytes(value).decode("utf-8", "strict")
    except (UnicodeDecodeError, ValueError):
        _raise("INVALID_DATABASE_CONFIG")
    if _contains_control(decoded):
        _raise("INVALID_DATABASE_CONFIG")
    return decoded


def _validate_database_identifier(value: str) -> str:
    if DATABASE_IDENTIFIER_PATTERN.fullmatch(value) is None or len(value.encode("utf-8")) > 63:
        _raise("INVALID_DATABASE_CONFIG")
    return value


def _validate_host(value: str) -> str:
    if (
        not value
        or len(value) > 253
        or _contains_control(value)
        or any(character.isspace() for character in value)
    ):
        _raise("INVALID_DATABASE_CONFIG")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,251}[A-Za-z0-9])?", value) is None:
        _raise("INVALID_DATABASE_CONFIG")
    return value


def _parse_database_query(query: str) -> tuple[tuple[str, str], ...]:
    if not query:
        return ()
    _validate_percent_escapes(query)
    try:
        pairs = urllib.parse.parse_qsl(
            query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            separator="&",
        )
    except (UnicodeDecodeError, ValueError):
        _raise("INVALID_DATABASE_CONFIG")

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for key, value in pairs:
        if (
            key in seen
            or not key
            or _contains_control(key)
            or _contains_control(value)
            or key in IDENTITY_QUERY_OPTIONS
        ):
            _raise("INVALID_DATABASE_CONFIG")
        seen.add(key)

        if key == "sslmode":
            if value not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
                _raise("INVALID_DATABASE_CONFIG")
            result.append(("PGSSLMODE", value))
        elif key in TLS_PATH_OPTIONS:
            if not value or len(value.encode("utf-8")) > 4_096:
                _raise("INVALID_DATABASE_CONFIG")
            result.append((TLS_PATH_OPTIONS[key], value))
        elif key == "channel_binding":
            if value not in {"disable", "prefer", "require"}:
                _raise("INVALID_DATABASE_CONFIG")
            result.append(("PGCHANNELBINDING", value))
        elif key == "gssencmode":
            if value not in {"disable", "prefer", "require"}:
                _raise("INVALID_DATABASE_CONFIG")
            result.append(("PGGSSENCMODE", value))
        elif key == "connect_timeout":
            try:
                numeric_timeout = int(value, 10)
            except ValueError:
                _raise("INVALID_DATABASE_CONFIG")
            if not 1 <= numeric_timeout <= 60 or str(numeric_timeout) != value:
                _raise("INVALID_DATABASE_CONFIG")
            result.append(("PGCONNECT_TIMEOUT", value))
        else:
            _raise("INVALID_DATABASE_CONFIG")
    return tuple(sorted(result))


def _parse_postgres_url(raw_url: str | None) -> PostgresConnection:
    if (
        not raw_url
        or len(raw_url.encode("utf-8")) > 8_192
        or _contains_control(raw_url)
        or "\\" in raw_url
        or "#" in raw_url
    ):
        _raise("INVALID_DATABASE_CONFIG")
    _validate_percent_escapes(raw_url)
    try:
        parsed = urllib.parse.urlsplit(raw_url, allow_fragments=True)
        port = parsed.port
    except ValueError:
        _raise("INVALID_DATABASE_CONFIG")

    host_authority = parsed.netloc.rsplit("@", 1)[-1]
    if (
        parsed.scheme not in {"postgresql", "postgresql+asyncpg"}
        or not parsed.netloc
        or host_authority.endswith(":")
        or parsed.fragment
        or parsed.username is None
        or parsed.hostname is None
        or not parsed.path.startswith("/")
        or parsed.path == "/"
    ):
        _raise("INVALID_DATABASE_CONFIG")

    username = _strict_unquote(parsed.username)
    password = _strict_unquote(parsed.password) if parsed.password is not None else ""
    host = _validate_host(_strict_unquote(parsed.hostname))
    database = _strict_unquote(parsed.path[1:])
    if not username or len(username.encode("utf-8")) > 128 or "/" in database:
        _raise("INVALID_DATABASE_CONFIG")
    database = _validate_database_identifier(database)
    effective_port = 5432 if port is None else port
    if not 1 <= effective_port <= 65_535:
        _raise("INVALID_DATABASE_CONFIG")
    options = _parse_database_query(parsed.query)
    return PostgresConnection(
        host=host,
        port=effective_port,
        username=username,
        password=password,
        database=database,
        option_environment=options,
    )


def _required_environment() -> str:
    environment = os.environ.get("IK_ENVIRONMENT")
    if environment not in KNOWN_ENVIRONMENTS:
        _raise("INVALID_ENVIRONMENT")
    return environment


def _release_commit(environment: str) -> str:
    value = os.environ.get("IK_RELEASE_COMMIT_SHA")
    if value is None:
        _raise("INVALID_RELEASE_IDENTITY")
    if value == "development":
        if environment in {"staging", "prod"}:
            _raise("INVALID_RELEASE_IDENTITY")
        return value
    if COMMIT_SHA_PATTERN.fullmatch(value) is None:
        _raise("INVALID_RELEASE_IDENTITY")
    return value


def _timeout(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= MAX_TIMEOUT_SECONDS:
        _raise("INVALID_ARGUMENT")
    return value


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_utc_timestamp(value: Any, reason_code: str) -> str:
    if type(value) is not str or UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        _raise(reason_code)
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    except ValueError:
        _raise(reason_code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _raise(reason_code)
    return value


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _write_json(value: dict[str, Any]) -> bool:
    try:
        sys.stdout.buffer.write(_canonical_json(value))
        sys.stdout.buffer.flush()
        return True
    except OSError:
        return False


def _json_object_no_duplicates(reason_code: str):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _raise(reason_code)
            result[key] = value
        return result

    return hook


def _parse_json_bytes(data: bytes, reason_code: str) -> Any:
    try:
        text = data.decode("utf-8", "strict")
        return json.loads(
            text,
            object_pairs_hook=_json_object_no_duplicates(reason_code),
            parse_constant=lambda _: _raise(reason_code),
        )
    except RecoveryError:
        raise
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        _raise(reason_code)


def _validate_revision_ids(value: Any, reason_code: str) -> list[str]:
    if type(value) is not list or not value or len(value) > 64:
        _raise(reason_code)
    revisions: list[str] = []
    for revision in value:
        if (
            type(revision) is not str
            or len(revision) > 128
            or REVISION_PATTERN.fullmatch(revision) is None
        ):
            _raise(reason_code)
        revisions.append(revision)
    if revisions != sorted(set(revisions)):
        _raise(reason_code)
    return revisions


def _validate_relative_text(value: str, reason_code: str) -> str:
    if (
        not value
        or len(value.encode("utf-8", "surrogatepass")) > 4_096
        or value.startswith("/")
        or "\\" in value
        or _contains_control(value)
        or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    ):
        _raise(reason_code)
    parts = value.split("/")
    if any(not part or part in {".", ".."} or len(part.encode("utf-8")) > 255 for part in parts):
        _raise(reason_code)
    return value


def _encode_relative_path(value: str, reason_code: str) -> str:
    validated = _validate_relative_text(value, reason_code)
    return urllib.parse.quote(validated, safe="/-._~", encoding="utf-8", errors="strict")


def _decode_relative_path(value: str, reason_code: str) -> str:
    if type(value) is not str or not value or len(value) > 12_288:
        _raise(reason_code)
    try:
        value.encode("ascii")
        decoded = urllib.parse.unquote_to_bytes(value).decode("utf-8", "strict")
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError):
        _raise(reason_code)
    validated = _validate_relative_text(decoded, reason_code)
    if _encode_relative_path(validated, reason_code) != value:
        _raise(reason_code)
    return validated


def _path_from_argument(value: str) -> Path:
    if not value or _contains_control(value):
        _raise("UNSAFE_FILESYSTEM")
    path = Path(value)
    if (
        not path.is_absolute()
        or path.anchor != os.sep
        or any(part in {"", ".", ".."} for part in path.parts[1:])
    ):
        _raise("UNSAFE_FILESYSTEM")
    return path


def _lstat_path_without_symlinks(path: Path) -> os.stat_result:
    cursor = Path(os.sep)
    result = os.lstat(cursor)
    allowed_owners = {0}
    if hasattr(os, "geteuid"):
        allowed_owners.add(os.geteuid())
    if (
        not stat.S_ISDIR(result.st_mode)
        or result.st_uid not in allowed_owners
        or stat.S_IMODE(result.st_mode) & 0o022
    ):
        _raise("UNSAFE_FILESYSTEM")
    components = path.parts[1:]
    for index, component in enumerate(components):
        cursor = cursor / component
        try:
            result = os.lstat(cursor)
        except OSError:
            _raise("UNSAFE_FILESYSTEM")
        if stat.S_ISLNK(result.st_mode):
            _raise("UNSAFE_FILESYSTEM")
        if index < len(components) - 1 and (
            not stat.S_ISDIR(result.st_mode)
            or result.st_uid not in allowed_owners
            or stat.S_IMODE(result.st_mode) & 0o022
        ):
            _raise("UNSAFE_FILESYSTEM")
    return result


def _assert_owned(stat_result: os.stat_result, reason_code: str) -> None:
    if hasattr(os, "geteuid") and stat_result.st_uid != os.geteuid():
        _raise(reason_code)


def _validate_output_root(value: str) -> Path:
    path = _path_from_argument(value)
    if path == Path(os.sep):
        _raise("UNSAFE_FILESYSTEM")
    result = _lstat_path_without_symlinks(path)
    if not stat.S_ISDIR(result.st_mode) or stat.S_IMODE(result.st_mode) & 0o022:
        _raise("UNSAFE_FILESYSTEM")
    _assert_owned(result, "UNSAFE_FILESYSTEM")
    return path


def _validate_private_directory(path: Path) -> None:
    result = _lstat_path_without_symlinks(path)
    if not stat.S_ISDIR(result.st_mode) or stat.S_IMODE(result.st_mode) != 0o700:
        _raise("BACKUP_INTEGRITY_FAILED")
    _assert_owned(result, "BACKUP_INTEGRITY_FAILED")


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags)
    except OSError:
        _raise("UNSAFE_FILESYSTEM")


def _create_backup_directory(root: Path, backup_name: str) -> tuple[Path, tuple[int, int]]:
    if BACKUP_NAME_PATTERN.fullmatch(backup_name) is None:
        _raise("INVALID_ARGUMENT")
    validated_root = _lstat_path_without_symlinks(root)
    root_fd = _open_directory(root)
    created = False
    try:
        opened_root = os.fstat(root_fd)
        if (
            (opened_root.st_dev, opened_root.st_ino)
            != (validated_root.st_dev, validated_root.st_ino)
            or not stat.S_ISDIR(opened_root.st_mode)
            or stat.S_IMODE(opened_root.st_mode) & 0o022
        ):
            _raise("UNSAFE_FILESYSTEM")
        _assert_owned(opened_root, "UNSAFE_FILESYSTEM")
        try:
            os.mkdir(backup_name, 0o700, dir_fd=root_fd)
            created = True
            directory_fd = os.open(
                backup_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_fd,
            )
            try:
                os.fchmod(directory_fd, 0o700)
                directory_result = os.fstat(directory_fd)
            finally:
                os.close(directory_fd)
            os.fsync(root_fd)
        except OSError:
            if created:
                try:
                    os.rmdir(backup_name, dir_fd=root_fd)
                except OSError:
                    _raise("BACKUP_CLEANUP_FAILED")
            _raise("UNSAFE_FILESYSTEM")
    finally:
        os.close(root_fd)
    return root / backup_name, (directory_result.st_dev, directory_result.st_ino)


def _remove_tree_contents_fd(
    directory_fd: int,
    expected_device: int,
    reason_code: str,
) -> None:
    try:
        with os.scandir(directory_fd) as iterator:
            entries = list(iterator)
    except OSError:
        _raise(reason_code)
    for entry in entries:
        try:
            result = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(result.st_mode) and not stat.S_ISLNK(result.st_mode):
                child_fd = os.open(
                    entry.name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    opened = os.fstat(child_fd)
                    if opened.st_dev != expected_device or (opened.st_dev, opened.st_ino) != (
                        result.st_dev,
                        result.st_ino,
                    ):
                        _raise(reason_code)
                    _remove_tree_contents_fd(child_fd, expected_device, reason_code)
                finally:
                    os.close(child_fd)
                current = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (result.st_dev, result.st_ino):
                    _raise(reason_code)
                os.rmdir(entry.name, dir_fd=directory_fd)
            else:
                os.unlink(entry.name, dir_fd=directory_fd)
        except RecoveryError:
            raise
        except OSError:
            _raise(reason_code)


def _remove_directory_by_identity(
    path: Path,
    parent: Path,
    identity: tuple[int, int],
    reason_code: str,
) -> None:
    if (
        path.parent != parent
        or path.name in {"", ".", ".."}
        or "/" in path.name
        or _contains_control(path.name)
    ):
        _raise(reason_code)
    root_fd: int | None = None
    directory_fd: int | None = None
    try:
        root_fd = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            result = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISDIR(result.st_mode) or (result.st_dev, result.st_ino) != identity:
            _raise(reason_code)
        directory_fd = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_fd,
        )
        opened = os.fstat(directory_fd)
        if (opened.st_dev, opened.st_ino) != identity:
            _raise(reason_code)
        _remove_tree_contents_fd(directory_fd, identity[0], reason_code)
        os.close(directory_fd)
        directory_fd = None
        current = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != identity:
            _raise(reason_code)
        os.rmdir(path.name, dir_fd=root_fd)
        os.fsync(root_fd)
    except RecoveryError:
        raise
    except OSError:
        _raise(reason_code)
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        if root_fd is not None:
            os.close(root_fd)


def _remove_created_directory(
    path: Path,
    root: Path,
    identity: tuple[int, int],
) -> None:
    if BACKUP_NAME_PATTERN.fullmatch(path.name) is None:
        _raise("BACKUP_CLEANUP_FAILED")
    _remove_directory_by_identity(
        path,
        root,
        identity,
        "BACKUP_CLEANUP_FAILED",
    )


def _create_empty_private_file(path: Path) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        _raise("UNSAFE_FILESYSTEM")
    try:
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        result = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    return (result.st_dev, result.st_ino)


def _assert_private_file_identity(path: Path, identity: tuple[int, int]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise("BACKUP_INTEGRITY_FAILED")
    try:
        result = os.fstat(descriptor)
        _check_private_file_stat(result, "BACKUP_INTEGRITY_FAILED")
        if (result.st_dev, result.st_ino) != identity:
            _raise("BACKUP_INTEGRITY_FAILED")
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: bytes) -> None:
    directory_fd = _open_directory(path.parent)
    temporary_name = f".{path.name}.tmp-{secrets.token_hex(8)}"
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _raise("UNSAFE_FILESYSTEM")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except RecoveryError:
        raise
    except OSError:
        _raise("UNSAFE_FILESYSTEM")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with contextlib.suppress(OSError):
            os.unlink(temporary_name, dir_fd=directory_fd)
        os.close(directory_fd)


def _check_private_file_stat(result: os.stat_result, reason_code: str) -> None:
    if (
        not stat.S_ISREG(result.st_mode)
        or stat.S_IMODE(result.st_mode) != 0o600
        or result.st_nlink != 1
    ):
        _raise(reason_code)
    _assert_owned(result, reason_code)


def _read_secure_file(path: Path, maximum_bytes: int, reason_code: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise(reason_code)
    try:
        before = os.fstat(descriptor)
        _check_private_file_stat(before, reason_code)
        if before.st_size > maximum_bytes:
            _raise(reason_code)
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(data) > maximum_bytes
            or before.st_ino != after.st_ino
            or before.st_dev != after.st_dev
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            _raise(reason_code)
        return data
    finally:
        os.close(descriptor)


def _hash_private_file(path: Path, reason_code: str) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise(reason_code)
    try:
        before = os.fstat(descriptor)
        _check_private_file_stat(before, reason_code)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_ino != after.st_ino
            or before.st_dev != after.st_dev
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or size != after.st_size
        ):
            _raise(reason_code)
        return digest.hexdigest(), size
    finally:
        os.close(descriptor)


def _inventory_private_tree(base: Path) -> tuple[set[str], set[str]]:
    _validate_private_directory(base)
    files: set[str] = set()
    directories: set[str] = set()
    stack: list[tuple[Path, str]] = [(base, "")]
    entries_seen = 0
    while stack:
        directory, relative_directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            _raise("BACKUP_INTEGRITY_FAILED")
        for entry in entries:
            entries_seen += 1
            if entries_seen > MAX_OBJECTS + 16:
                _raise("BACKUP_INTEGRITY_FAILED")
            relative = f"{relative_directory}/{entry.name}" if relative_directory else entry.name
            _validate_relative_text(relative, "BACKUP_INTEGRITY_FAILED")
            try:
                result = entry.stat(follow_symlinks=False)
            except OSError:
                _raise("BACKUP_INTEGRITY_FAILED")
            if stat.S_ISLNK(result.st_mode):
                _raise("BACKUP_INTEGRITY_FAILED")
            if stat.S_ISDIR(result.st_mode):
                if stat.S_IMODE(result.st_mode) != 0o700:
                    _raise("BACKUP_INTEGRITY_FAILED")
                _assert_owned(result, "BACKUP_INTEGRITY_FAILED")
                directories.add(relative)
                stack.append((Path(entry.path), relative))
            elif stat.S_ISREG(result.st_mode):
                _check_private_file_stat(result, "BACKUP_INTEGRITY_FAILED")
                files.add(relative)
            else:
                _raise("BACKUP_INTEGRITY_FAILED")
    return files, directories


def _prepare_object_tree(root: Path, reason_code: str) -> None:
    try:
        root_result = os.lstat(root)
    except OSError:
        _raise(reason_code)
    if not stat.S_ISDIR(root_result.st_mode) or stat.S_ISLNK(root_result.st_mode):
        _raise(reason_code)
    root_fd = _open_directory(root)
    try:
        os.fchmod(root_fd, 0o700)
    finally:
        os.close(root_fd)

    stack = [root]
    entries_seen = 0
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            _raise(reason_code)
        for entry in entries:
            entries_seen += 1
            if entries_seen > MAX_OBJECTS + 8:
                _raise(reason_code)
            try:
                relative = str(Path(entry.path).relative_to(root))
            except ValueError:
                _raise(reason_code)
            _validate_relative_text(relative, reason_code)
            try:
                result = entry.stat(follow_symlinks=False)
            except OSError:
                _raise(reason_code)
            if stat.S_ISLNK(result.st_mode):
                _raise(reason_code)
            if stat.S_ISDIR(result.st_mode):
                descriptor = _open_directory(Path(entry.path))
                try:
                    os.fchmod(descriptor, 0o700)
                finally:
                    os.close(descriptor)
                stack.append(Path(entry.path))
            elif stat.S_ISREG(result.st_mode) and result.st_nlink == 1:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                descriptor: int | None = None
                try:
                    descriptor = os.open(entry.path, flags)
                    os.fchmod(descriptor, 0o600)
                except OSError:
                    _raise(reason_code)
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
            else:
                _raise(reason_code)


def _object_aggregate(root: Path, reason_code: str) -> ObjectAggregate:
    try:
        result = os.lstat(root)
    except OSError:
        _raise(reason_code)
    if not stat.S_ISDIR(result.st_mode) or stat.S_IMODE(result.st_mode) != 0o700:
        _raise(reason_code)
    _assert_owned(result, reason_code)

    entries: list[ObjectEntry] = []
    directories: set[str] = set()
    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        directory, relative_directory = stack.pop()
        try:
            children = list(os.scandir(directory))
        except OSError:
            _raise(reason_code)
        for child in children:
            relative = f"{relative_directory}/{child.name}" if relative_directory else child.name
            _validate_relative_text(relative, reason_code)
            try:
                child_stat = child.stat(follow_symlinks=False)
            except OSError:
                _raise(reason_code)
            if stat.S_ISLNK(child_stat.st_mode):
                _raise(reason_code)
            if stat.S_ISDIR(child_stat.st_mode):
                if stat.S_IMODE(child_stat.st_mode) != 0o700:
                    _raise(reason_code)
                _assert_owned(child_stat, reason_code)
                directories.add(relative)
                stack.append((Path(child.path), relative))
            elif stat.S_ISREG(child_stat.st_mode):
                if len(entries) >= MAX_OBJECTS:
                    _raise(reason_code)
                checksum, size = _hash_private_file(Path(child.path), reason_code)
                entries.append(
                    ObjectEntry(
                        relative_path=relative,
                        encoded_path=_encode_relative_path(relative, reason_code),
                        sha256=checksum,
                        size_bytes=size,
                    )
                )
            else:
                _raise(reason_code)

    expected_directories: set[str] = set()
    for entry in entries:
        parts = entry.relative_path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            expected_directories.add("/".join(parts[:index]))
    if directories != expected_directories:
        _raise(reason_code)

    ordered = tuple(sorted(entries, key=lambda item: item.encoded_path))
    aggregate = hashlib.sha256(OBJECT_DIGEST_DOMAIN)
    total_bytes = 0
    for entry in ordered:
        encoded = entry.encoded_path.encode("ascii")
        aggregate.update(len(encoded).to_bytes(8, "big"))
        aggregate.update(encoded)
        aggregate.update(entry.size_bytes.to_bytes(8, "big"))
        aggregate.update(bytes.fromhex(entry.sha256))
        total_bytes += entry.size_bytes
    return ObjectAggregate(
        aggregate_sha256=aggregate.hexdigest(),
        object_count=len(ordered),
        total_bytes=total_bytes,
        entries=ordered,
    )


def _resolve_tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        _raise("PREREQUISITE_UNAVAILABLE")
    unresolved_path = Path(resolved)
    if not unresolved_path.is_absolute():
        _raise("PREREQUISITE_UNAVAILABLE")
    try:
        path = unresolved_path.resolve(strict=True)
    except OSError:
        _raise("PREREQUISITE_UNAVAILABLE")

    allowed_owners = {0}
    if hasattr(os, "geteuid"):
        allowed_owners.add(os.geteuid())
    cursor = Path(os.sep)
    for component in path.parts[1:-1]:
        cursor = cursor / component
        try:
            directory_result = os.lstat(cursor)
        except OSError:
            _raise("PREREQUISITE_UNAVAILABLE")
        if (
            not stat.S_ISDIR(directory_result.st_mode)
            or stat.S_ISLNK(directory_result.st_mode)
            or directory_result.st_uid not in allowed_owners
            or stat.S_IMODE(directory_result.st_mode) & 0o022
        ):
            _raise("PREREQUISITE_UNAVAILABLE")
    try:
        result = os.lstat(path)
    except OSError:
        _raise("PREREQUISITE_UNAVAILABLE")
    if (
        not stat.S_ISREG(result.st_mode)
        or stat.S_ISLNK(result.st_mode)
        or result.st_uid not in allowed_owners
        or stat.S_IMODE(result.st_mode) & 0o022
        or not os.access(path, os.X_OK)
    ):
        _raise("PREREQUISITE_UNAVAILABLE")
    return str(path)


def _run_command(
    arguments: Sequence[str],
    *,
    environment: dict[str, str],
    timeout_seconds: int,
    failure_code: str,
    capture_stdout: bool = False,
) -> bytes:
    try:
        completed = subprocess.run(
            list(arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            cwd=os.sep,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            close_fds=True,
        )
    except subprocess.TimeoutExpired:
        _raise("OPERATION_TIMEOUT")
    except OSError:
        _raise(failure_code)
    if completed.returncode != 0:
        _raise(failure_code)
    return completed.stdout if capture_stdout else b""


def _require_tool_help(
    executable: str,
    required_tokens: Sequence[str],
    timeout_seconds: int,
) -> None:
    output = _run_command(
        (executable, "--help"),
        environment=_base_child_environment(),
        timeout_seconds=min(timeout_seconds, 30),
        failure_code="PREREQUISITE_UNAVAILABLE",
        capture_stdout=True,
    )
    if len(output) > 65_536:
        _raise("PREREQUISITE_UNAVAILABLE")
    try:
        help_text = output.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _raise("PREREQUISITE_UNAVAILABLE")
    if any(token not in help_text for token in required_tokens):
        _raise("PREREQUISITE_UNAVAILABLE")


def _base_child_environment() -> dict[str, str]:
    return {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "TZ": "UTC",
    }


def _escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


@contextlib.contextmanager
def _postgres_environment(
    connection: PostgresConnection,
    *,
    database: str,
    timeout_seconds: int,
    additional_databases: Sequence[str] = (),
) -> Iterator[dict[str, str]]:
    interrupted = [False]
    previous_handlers = _install_deferred_signal_handlers(interrupted)
    temporary_directory: Path | None = None
    pgpass_path: Path | None = None
    try:
        temporary_directory = Path(tempfile.mkdtemp(prefix="ik-recovery-pg-"))
        pgpass_path = temporary_directory / "pgpass"
        os.chmod(temporary_directory, 0o700)
        pgpass_lines = []
        for pass_database in (database, *additional_databases):
            pgpass_lines.append(
                ":".join(
                    _escape_pgpass(component)
                    for component in (
                        connection.host,
                        str(connection.port),
                        pass_database,
                        connection.username,
                        connection.password,
                    )
                )
            )
        descriptor = os.open(
            pgpass_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            remaining = memoryview(("\n".join(pgpass_lines) + "\n").encode("utf-8"))
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    _raise("TEMPORARY_CLEANUP_FAILED")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        environment = _base_child_environment()
        environment.update(
            {
                "PGAPPNAME": "ik-recovery",
                "PGCONNECT_TIMEOUT": str(min(timeout_seconds, 30)),
                "PGDATABASE": database,
                "PGHOST": connection.host,
                "PGPASSFILE": str(pgpass_path),
                "PGPORT": str(connection.port),
                "PGUSER": connection.username,
            }
        )
        environment.update(dict(connection.option_environment))
        yield environment
    finally:
        active_exception = sys.exception()
        cleanup_failed = False
        if pgpass_path is not None:
            try:
                pgpass_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        if temporary_directory is not None:
            try:
                temporary_directory.rmdir()
            except OSError:
                cleanup_failed = True
        _restore_signal_handlers(previous_handlers)
        if cleanup_failed:
            _raise("TEMPORARY_CLEANUP_FAILED")
        if interrupted[0] and active_exception is None:
            _raise("INTERRUPTED")


def _mc_environment() -> dict[str, str]:
    environment = _base_child_environment()
    home = os.environ.get("HOME")
    config_directory = os.environ.get("MC_CONFIG_DIR")
    if home is not None:
        if _contains_control(home) or not Path(home).is_absolute():
            _raise("INVALID_STORAGE_CONFIG")
        environment["HOME"] = home
    if config_directory is not None:
        if _contains_control(config_directory) or not Path(config_directory).is_absolute():
            _raise("INVALID_STORAGE_CONFIG")
        environment["MC_CONFIG_DIR"] = config_directory
    if "HOME" not in environment and "MC_CONFIG_DIR" not in environment:
        _raise("INVALID_STORAGE_CONFIG")
    return environment


def _psql_output(
    psql: str,
    environment: dict[str, str],
    sql: str,
    timeout_seconds: int,
    failure_code: str,
) -> str:
    output = _run_command(
        (
            psql,
            "--no-password",
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            "--tuples-only",
            "--no-align",
            "--quiet",
            "--command",
            sql,
        ),
        environment=environment,
        timeout_seconds=timeout_seconds,
        failure_code=failure_code,
        capture_stdout=True,
    )
    if len(output) > 65_536:
        _raise(failure_code)
    try:
        return output.decode("ascii", "strict").strip()
    except UnicodeDecodeError:
        _raise(failure_code)


def _query_revisions(
    psql: str,
    environment: dict[str, str],
    timeout_seconds: int,
    failure_code: str,
) -> list[str]:
    output = _psql_output(
        psql,
        environment,
        "SELECT version_num FROM public.alembic_version ORDER BY version_num LIMIT 65;",
        timeout_seconds,
        failure_code,
    )
    revisions = [line.strip() for line in output.splitlines() if line.strip()]
    if not revisions or len(revisions) > 64:
        _raise("MIGRATION_REVISION_INVALID")
    for revision in revisions:
        if len(revision) > 128 or REVISION_PATTERN.fullmatch(revision) is None:
            _raise("MIGRATION_REVISION_INVALID")
    if len(revisions) != len(set(revisions)):
        _raise("MIGRATION_REVISION_INVALID")
    return sorted(revisions)


def _validate_alias(value: str | None) -> str:
    if value is None or ALIAS_PATTERN.fullmatch(value) is None:
        _raise("INVALID_STORAGE_CONFIG")
    return value


def _validate_bucket(value: str | None) -> str:
    if (
        value is None
        or not 3 <= len(value) <= 63
        or re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", value) is None
        or ".." in value
        or ".-" in value
        or "-." in value
    ):
        _raise("INVALID_STORAGE_CONFIG")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    _raise("INVALID_STORAGE_CONFIG")


def _storage_source_configuration() -> tuple[str, str, str]:
    backend = os.environ.get("IK_DOCUMENT_STORAGE_BACKEND")
    if backend == "disabled":
        return backend, "", ""
    if backend != "s3":
        _raise("INVALID_STORAGE_CONFIG")
    alias = _validate_alias(os.environ.get("IK_RECOVERY_MC_SOURCE_ALIAS"))
    bucket = _validate_bucket(os.environ.get("IK_S3_BUCKET"))
    return backend, alias, bucket


def _make_private_directory(path: Path, reason_code: str) -> None:
    try:
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
    except OSError:
        _raise(reason_code)


def _mirror_objects_for_backup(
    mc: str,
    alias: str,
    bucket: str,
    objects_directory: Path,
    timeout_seconds: int,
) -> ObjectAggregate:
    _make_private_directory(objects_directory, "OBJECT_OPERATION_FAILED")
    _run_command(
        (mc, "mirror", "--quiet", f"{alias}/{bucket}", str(objects_directory)),
        environment=_mc_environment(),
        timeout_seconds=timeout_seconds,
        failure_code="OBJECT_OPERATION_FAILED",
    )
    _prepare_object_tree(objects_directory, "OBJECT_OPERATION_FAILED")
    return _object_aggregate(objects_directory, "OBJECT_OPERATION_FAILED")


def _manifest(
    *,
    created_at: str,
    database_name: str,
    revisions: list[str],
    release_commit: str,
    dump_sha256: str,
    dump_size: int,
    object_aggregate: ObjectAggregate | None,
) -> dict[str, Any]:
    object_storage: dict[str, Any]
    if object_aggregate is None:
        object_storage = {"state": "not_applicable"}
    else:
        object_storage = {
            "aggregate_sha256": object_aggregate.aggregate_sha256,
            "object_count": object_aggregate.object_count,
            "state": "included",
            "total_bytes": object_aggregate.total_bytes,
        }
    return {
        "backup_format": BACKUP_FORMAT,
        "created_at_utc": created_at,
        "database_dump": {"sha256": dump_sha256, "size_bytes": dump_size},
        "database_name": database_name,
        "object_storage": object_storage,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "source_migration_revision_ids": revisions,
        "source_release_commit_sha": release_commit,
    }


def _checksum_contents(
    backup_directory: Path,
    object_aggregate: ObjectAggregate | None,
) -> bytes:
    artifacts: list[tuple[str, str]] = []
    for relative in (DATABASE_DUMP_NAME, MANIFEST_NAME):
        checksum, _ = _hash_private_file(
            backup_directory / relative,
            "BACKUP_INTEGRITY_FAILED",
        )
        artifacts.append((_encode_relative_path(relative, "BACKUP_INTEGRITY_FAILED"), checksum))
    if object_aggregate is not None:
        for entry in object_aggregate.entries:
            relative = f"{OBJECTS_DIRECTORY_NAME}/{entry.relative_path}"
            artifacts.append(
                (_encode_relative_path(relative, "BACKUP_INTEGRITY_FAILED"), entry.sha256)
            )
    artifacts.sort(key=lambda item: item[0])
    return "".join(f"{checksum}  {encoded}\n" for encoded, checksum in artifacts).encode("ascii")


def _validate_manifest(value: Any, canonical_data: bytes) -> dict[str, Any]:
    reason = "BACKUP_SCHEMA_INVALID"
    if type(value) is not dict or set(value) != {
        "backup_format",
        "created_at_utc",
        "database_dump",
        "database_name",
        "object_storage",
        "schema_version",
        "source_migration_revision_ids",
        "source_release_commit_sha",
    }:
        _raise(reason)
    if _canonical_json(value) != canonical_data:
        _raise(reason)
    if (
        value["backup_format"] != BACKUP_FORMAT
        or type(value["schema_version"]) is not int
        or value["schema_version"] != BACKUP_SCHEMA_VERSION
    ):
        _raise(reason)
    _validate_utc_timestamp(value["created_at_utc"], reason)
    if type(value["database_name"]) is not str:
        _raise(reason)
    try:
        _validate_database_identifier(value["database_name"])
    except RecoveryError:
        _raise(reason)
    _validate_revision_ids(value["source_migration_revision_ids"], reason)
    release_commit = value["source_release_commit_sha"]
    if release_commit != "development" and (
        type(release_commit) is not str or COMMIT_SHA_PATTERN.fullmatch(release_commit) is None
    ):
        _raise(reason)

    dump = value["database_dump"]
    if type(dump) is not dict or set(dump) != {"sha256", "size_bytes"}:
        _raise(reason)
    if type(dump["sha256"]) is not str or HEX_SHA256_PATTERN.fullmatch(dump["sha256"]) is None:
        _raise(reason)
    if type(dump["size_bytes"]) is not int or not 0 < dump["size_bytes"] < 2**63:
        _raise(reason)

    storage = value["object_storage"]
    if type(storage) is not dict or "state" not in storage:
        _raise(reason)
    if storage["state"] == "not_applicable":
        if set(storage) != {"state"}:
            _raise(reason)
    elif storage["state"] == "included":
        if set(storage) != {"aggregate_sha256", "object_count", "state", "total_bytes"}:
            _raise(reason)
        if (
            type(storage["aggregate_sha256"]) is not str
            or HEX_SHA256_PATTERN.fullmatch(storage["aggregate_sha256"]) is None
            or type(storage["object_count"]) is not int
            or not 0 <= storage["object_count"] <= MAX_OBJECTS
            or type(storage["total_bytes"]) is not int
            or not 0 <= storage["total_bytes"] < 2**63
        ):
            _raise(reason)
    else:
        _raise(reason)
    return value


def _parse_checksums(data: bytes) -> dict[str, str]:
    reason = "BACKUP_INTEGRITY_FAILED"
    if not data or not data.endswith(b"\n") or b"\r" in data or b"\x00" in data:
        _raise(reason)
    try:
        text = data.decode("ascii", "strict")
    except UnicodeDecodeError:
        _raise(reason)
    result: dict[str, str] = {}
    encoded_order: list[str] = []
    for line in text.splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            _raise(reason)
        checksum = line[:64]
        encoded = line[66:]
        if HEX_SHA256_PATTERN.fullmatch(checksum) is None:
            _raise(reason)
        relative = _decode_relative_path(encoded, reason)
        if relative == CHECKSUMS_NAME or relative in result:
            _raise(reason)
        result[relative] = checksum
        encoded_order.append(encoded)
    if encoded_order != sorted(encoded_order) or len(encoded_order) != len(set(encoded_order)):
        _raise(reason)
    return result


def _expected_directories(files: set[str], object_state: str) -> set[str]:
    expected: set[str] = set()
    if object_state == "included":
        expected.add(OBJECTS_DIRECTORY_NAME)
    for relative in files:
        parts = relative.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            expected.add("/".join(parts[:index]))
    return expected


def _verify_integrity_pass(
    backup_directory: Path,
    manifest: dict[str, Any],
    checksums: dict[str, str],
    expected_files: set[str],
    expected_directories: set[str],
) -> None:
    actual_files, actual_directories = _inventory_private_tree(backup_directory)
    if actual_files != expected_files or actual_directories != expected_directories:
        _raise("BACKUP_INTEGRITY_FAILED")
    sizes: dict[str, int] = {}
    for relative, expected_checksum in checksums.items():
        checksum, size = _hash_private_file(
            backup_directory / relative,
            "BACKUP_INTEGRITY_FAILED",
        )
        if checksum != expected_checksum:
            _raise("BACKUP_INTEGRITY_FAILED")
        sizes[relative] = size

    dump = manifest["database_dump"]
    if (
        checksums[DATABASE_DUMP_NAME] != dump["sha256"]
        or sizes[DATABASE_DUMP_NAME] != dump["size_bytes"]
    ):
        _raise("BACKUP_INTEGRITY_FAILED")

    storage = manifest["object_storage"]
    if storage["state"] == "included":
        aggregate = _object_aggregate(
            backup_directory / OBJECTS_DIRECTORY_NAME,
            "BACKUP_INTEGRITY_FAILED",
        )
        expected_object_paths = {
            f"{OBJECTS_DIRECTORY_NAME}/{entry.relative_path}" for entry in aggregate.entries
        }
        actual_object_paths = {
            relative for relative in checksums if relative.startswith(f"{OBJECTS_DIRECTORY_NAME}/")
        }
        if (
            expected_object_paths != actual_object_paths
            or aggregate.aggregate_sha256 != storage["aggregate_sha256"]
            or aggregate.object_count != storage["object_count"]
            or aggregate.total_bytes != storage["total_bytes"]
        ):
            _raise("BACKUP_INTEGRITY_FAILED")


def _verify_backup(backup_directory_value: str, timeout_seconds: int) -> VerifiedBackup:
    backup_directory = _path_from_argument(backup_directory_value)
    _validate_private_directory(backup_directory)
    files, directories = _inventory_private_tree(backup_directory)
    if MANIFEST_NAME not in files or CHECKSUMS_NAME not in files or DATABASE_DUMP_NAME not in files:
        _raise("BACKUP_INTEGRITY_FAILED")

    manifest_data = _read_secure_file(
        backup_directory / MANIFEST_NAME,
        MAX_JSON_BYTES,
        "BACKUP_SCHEMA_INVALID",
    )
    manifest_value = _parse_json_bytes(manifest_data, "BACKUP_SCHEMA_INVALID")
    manifest = _validate_manifest(manifest_value, manifest_data)
    checksum_data = _read_secure_file(
        backup_directory / CHECKSUMS_NAME,
        MAX_CHECKSUM_BYTES,
        "BACKUP_INTEGRITY_FAILED",
    )
    checksums = _parse_checksums(checksum_data)
    if DATABASE_DUMP_NAME not in checksums or MANIFEST_NAME not in checksums:
        _raise("BACKUP_INTEGRITY_FAILED")
    if checksums.get(MANIFEST_NAME) != hashlib.sha256(manifest_data).hexdigest():
        _raise("BACKUP_INTEGRITY_FAILED")

    storage_state = manifest["object_storage"]["state"]
    for relative in checksums:
        if relative in {DATABASE_DUMP_NAME, MANIFEST_NAME}:
            continue
        if storage_state == "included" and relative.startswith(f"{OBJECTS_DIRECTORY_NAME}/"):
            continue
        _raise("BACKUP_INTEGRITY_FAILED")
    if storage_state == "not_applicable" and any(
        relative.startswith(f"{OBJECTS_DIRECTORY_NAME}/") for relative in checksums
    ):
        _raise("BACKUP_INTEGRITY_FAILED")
    expected_files = set(checksums) | {CHECKSUMS_NAME}
    expected_directories = _expected_directories(set(checksums), storage_state)
    if files != expected_files or directories != expected_directories:
        _raise("BACKUP_INTEGRITY_FAILED")

    _verify_integrity_pass(
        backup_directory,
        manifest,
        checksums,
        expected_files,
        expected_directories,
    )
    pg_restore = _resolve_tool("pg_restore")
    _run_command(
        (pg_restore, "--list", str(backup_directory / DATABASE_DUMP_NAME)),
        environment=_base_child_environment(),
        timeout_seconds=timeout_seconds,
        failure_code="ARCHIVE_INVALID",
    )
    _verify_integrity_pass(
        backup_directory,
        manifest,
        checksums,
        expected_files,
        expected_directories,
    )
    return VerifiedBackup(backup_directory=backup_directory, manifest=manifest)


def _backup(args: argparse.Namespace) -> dict[str, Any]:
    timeout_seconds = _timeout(args.timeout_seconds)
    environment_name = _required_environment()
    source = _parse_postgres_url(os.environ.get("IK_DATABASE_URL"))
    release_commit = _release_commit(environment_name)
    backend, source_alias, source_bucket = _storage_source_configuration()
    output_root = _validate_output_root(args.output_root)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"backup-{stamp}-{secrets.token_hex(4)}"

    pg_dump = _resolve_tool("pg_dump")
    psql = _resolve_tool("psql")
    _resolve_tool("alembic")
    _resolve_tool("pg_restore")
    mc = _resolve_tool("mc") if backend == "s3" else None

    backup_directory, backup_directory_identity = _create_backup_directory(
        output_root,
        backup_name,
    )
    completed = False
    try:
        dump_path = backup_directory / DATABASE_DUMP_NAME
        dump_identity = _create_empty_private_file(dump_path)
        created_at = _utc_now()
        with _postgres_environment(
            source,
            database=source.database,
            timeout_seconds=timeout_seconds,
        ) as postgres_environment:
            revisions_before = _query_revisions(
                psql,
                postgres_environment,
                timeout_seconds,
                "BACKUP_COMMAND_FAILED",
            )
            _run_command(
                (
                    pg_dump,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--no-password",
                    "--file",
                    str(dump_path),
                ),
                environment=postgres_environment,
                timeout_seconds=timeout_seconds,
                failure_code="BACKUP_COMMAND_FAILED",
            )
            revisions_after = _query_revisions(
                psql,
                postgres_environment,
                timeout_seconds,
                "BACKUP_COMMAND_FAILED",
            )
        if revisions_before != revisions_after:
            _raise("BACKUP_CONSISTENCY_FAILED")
        _assert_private_file_identity(dump_path, dump_identity)
        dump_sha256, dump_size = _hash_private_file(dump_path, "BACKUP_INTEGRITY_FAILED")
        if dump_size == 0:
            _raise("BACKUP_COMMAND_FAILED")

        object_aggregate: ObjectAggregate | None = None
        if backend == "s3":
            if mc is None:
                _raise("PREREQUISITE_UNAVAILABLE")
            object_aggregate = _mirror_objects_for_backup(
                mc,
                source_alias,
                source_bucket,
                backup_directory / OBJECTS_DIRECTORY_NAME,
                timeout_seconds,
            )

        manifest = _manifest(
            created_at=created_at,
            database_name=source.database,
            revisions=revisions_after,
            release_commit=release_commit,
            dump_sha256=dump_sha256,
            dump_size=dump_size,
            object_aggregate=object_aggregate,
        )
        _atomic_write(backup_directory / MANIFEST_NAME, _canonical_json(manifest))
        _atomic_write(
            backup_directory / CHECKSUMS_NAME,
            _checksum_contents(backup_directory, object_aggregate),
        )
        _verify_backup(str(backup_directory), timeout_seconds)
        completed = True
        return {
            "backup_name": backup_name,
            "completed_at_utc": _utc_now(),
            "status": "completed",
        }
    finally:
        if not completed:
            _remove_created_directory(
                backup_directory,
                output_root,
                backup_directory_identity,
            )


def _verify_backup_command(args: argparse.Namespace) -> dict[str, Any]:
    environment = _required_environment()
    verified = _verify_backup(args.backup_dir, _timeout(args.timeout_seconds))
    if (
        environment in {"staging", "prod"}
        and verified.manifest["source_release_commit_sha"] == "development"
    ):
        _raise("BACKUP_SCHEMA_INVALID")
    return {"status": "verified", "verified_at_utc": _utc_now()}


@contextlib.contextmanager
def _private_temporary_directory(prefix: str) -> Iterator[Path]:
    interrupted = [False]
    previous_handlers = _install_deferred_signal_handlers(interrupted)
    path: Path | None = None
    identity: tuple[int, int] | None = None
    try:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        initial = os.lstat(path)
        identity = (initial.st_dev, initial.st_ino)
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != identity:
                _raise("TEMPORARY_CLEANUP_FAILED")
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)
        yield path
    finally:
        active_exception = sys.exception()
        cleanup_error: RecoveryError | None = None
        try:
            if path is not None and identity is not None:
                try:
                    _remove_directory_by_identity(
                        path,
                        path.parent,
                        identity,
                        "TEMPORARY_CLEANUP_FAILED",
                    )
                except RecoveryError as error:
                    cleanup_error = error
        finally:
            _restore_signal_handlers(previous_handlers)
        if cleanup_error is not None:
            raise cleanup_error
        if interrupted[0] and active_exception is None:
            _raise("INTERRUPTED")


def _remote_object_aggregate(
    mc: str,
    target: str,
    timeout_seconds: int,
) -> ObjectAggregate:
    with _private_temporary_directory("ik-recovery-objects-") as temporary:
        _run_command(
            (mc, "mirror", "--quiet", target, str(temporary)),
            environment=_mc_environment(),
            timeout_seconds=timeout_seconds,
            failure_code="OBJECT_OPERATION_FAILED",
        )
        _prepare_object_tree(temporary, "OBJECT_OPERATION_FAILED")
        return _object_aggregate(temporary, "OBJECT_OPERATION_FAILED")


def _proof_object_configuration(
    args: argparse.Namespace,
    verified: VerifiedBackup,
) -> tuple[str, str, str, str] | None:
    if not args.include_objects:
        if args.proof_object_alias is not None or args.proof_object_bucket is not None:
            _raise("RESTORE_GUARD_REJECTED")
        return None
    if verified.manifest["object_storage"]["state"] != "included":
        _raise("RESTORE_GUARD_REJECTED")
    if os.environ.get("IK_DOCUMENT_STORAGE_BACKEND") != "s3":
        _raise("INVALID_STORAGE_CONFIG")
    source_alias = _validate_alias(os.environ.get("IK_RECOVERY_MC_SOURCE_ALIAS"))
    source_bucket = _validate_bucket(os.environ.get("IK_S3_BUCKET"))
    proof_alias = _validate_alias(args.proof_object_alias)
    proof_bucket = _validate_bucket(args.proof_object_bucket)
    if proof_alias == source_alias or proof_bucket == source_bucket:
        _raise("RESTORE_GUARD_REJECTED")
    return source_alias, source_bucket, proof_alias, proof_bucket


def _ensure_proof_bucket_empty(
    mc: str,
    proof_alias: str,
    proof_bucket: str,
    timeout_seconds: int,
) -> None:
    aggregate = _remote_object_aggregate(mc, f"{proof_alias}/{proof_bucket}", timeout_seconds)
    if aggregate.object_count != 0 or aggregate.total_bytes != 0:
        _raise("RESTORE_GUARD_REJECTED")


def _restore_and_verify_objects(
    mc: str,
    verified: VerifiedBackup,
    proof_alias: str,
    proof_bucket: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    target = f"{proof_alias}/{proof_bucket}"
    _ensure_proof_bucket_empty(mc, proof_alias, proof_bucket, timeout_seconds)
    _run_command(
        (
            mc,
            "mirror",
            "--quiet",
            str(verified.backup_directory / OBJECTS_DIRECTORY_NAME),
            target,
        ),
        environment=_mc_environment(),
        timeout_seconds=timeout_seconds,
        failure_code="OBJECT_OPERATION_FAILED",
    )
    restored = _remote_object_aggregate(mc, target, timeout_seconds)
    expected = verified.manifest["object_storage"]
    if (
        restored.aggregate_sha256 != expected["aggregate_sha256"]
        or restored.object_count != expected["object_count"]
        or restored.total_bytes != expected["total_bytes"]
    ):
        _raise("RESTORE_VALIDATION_FAILED")
    return {
        "object_count": restored.object_count,
        "status": "verified",
        "total_bytes": restored.total_bytes,
    }


def _proof_database_name(value: str, source: PostgresConnection, admin: PostgresConnection) -> str:
    if (
        PROOF_DATABASE_PATTERN.fullmatch(value) is None
        or len(value.encode("ascii", "strict")) > 63
        or value in PROTECTED_DATABASE_NAMES
        or value in {source.database, admin.database}
    ):
        _raise("RESTORE_GUARD_REJECTED")
    return value


def _proof_database_exists(
    psql: str,
    maintenance_environment: dict[str, str],
    proof_database: str,
    timeout_seconds: int,
    failure_code: str,
) -> bool:
    value = _psql_output(
        psql,
        maintenance_environment,
        f"SELECT count(*) FROM pg_catalog.pg_database WHERE datname = '{proof_database}';",
        timeout_seconds,
        failure_code,
    )
    if value not in {"0", "1"}:
        _raise(failure_code)
    return value == "1"


def _proof_database_identity(
    psql: str,
    maintenance_environment: dict[str, str],
    proof_database: str,
    timeout_seconds: int,
    failure_code: str,
) -> tuple[int, int, int, str] | None:
    value = _psql_output(
        psql,
        maintenance_environment,
        "SELECT oid::text || '|' || datdba::text || '|' || datconnlimit::text || '|' || "
        "COALESCE(pg_catalog.shobj_description(oid, 'pg_database'), '') "
        "FROM pg_catalog.pg_database "
        f"WHERE datname = '{proof_database}';",
        timeout_seconds,
        failure_code,
    )
    if not value:
        return None
    oid_text, separator, remainder = value.partition("|")
    owner_text, second_separator, remainder = remainder.partition("|")
    connection_limit_text, third_separator, marker = remainder.partition("|")
    if (
        not separator
        or not second_separator
        or not third_separator
        or not oid_text.isdigit()
        or not owner_text.isdigit()
        or (connection_limit_text != "-1" and not connection_limit_text.isdigit())
    ):
        _raise(failure_code)
    oid = int(oid_text)
    owner_oid = int(owner_text)
    connection_limit = int(connection_limit_text)
    if oid <= 0 or owner_oid <= 0 or connection_limit < -1:
        _raise(failure_code)
    return oid, owner_oid, connection_limit, marker


def _proof_database_oid_exists(
    psql: str,
    maintenance_environment: dict[str, str],
    proof_oid: int,
    timeout_seconds: int,
    failure_code: str,
) -> bool:
    value = _psql_output(
        psql,
        maintenance_environment,
        f"SELECT count(*) FROM pg_catalog.pg_database WHERE oid = {proof_oid};",
        timeout_seconds,
        failure_code,
    )
    if value not in {"0", "1"}:
        _raise(failure_code)
    return value == "1"


def _proof_database_marker_exists(
    psql: str,
    maintenance_environment: dict[str, str],
    proof_marker: str,
    timeout_seconds: int,
    failure_code: str,
) -> bool:
    value = _psql_output(
        psql,
        maintenance_environment,
        "SELECT count(*) FROM pg_catalog.pg_database "
        "WHERE pg_catalog.shobj_description(oid, 'pg_database') "
        f"= '{proof_marker}';",
        timeout_seconds,
        failure_code,
    )
    if value not in {"0", "1"}:
        _raise(failure_code)
    return value == "1"


def _proof_database_connection_limit_exists(
    psql: str,
    maintenance_environment: dict[str, str],
    connection_limit: int,
    timeout_seconds: int,
    failure_code: str,
) -> bool:
    value = _psql_output(
        psql,
        maintenance_environment,
        f"SELECT count(*) FROM pg_catalog.pg_database WHERE datconnlimit = {connection_limit};",
        timeout_seconds,
        failure_code,
    )
    if value not in {"0", "1"}:
        _raise(failure_code)
    return value == "1"


def _cleanup_proof_database(
    dropdb: str,
    psql: str,
    maintenance_environment: dict[str, str],
    proof_database: str,
    proof_marker: str,
    proof_oid: int | None,
    proof_owner_oid: int,
    proof_connection_limit: int,
    timeout_seconds: int,
) -> None:
    try:
        current_identity = _proof_database_identity(
            psql,
            maintenance_environment,
            proof_database,
            timeout_seconds,
            "PROOF_CLEANUP_FAILED",
        )
        if current_identity is None:
            if proof_oid is not None and _proof_database_oid_exists(
                psql,
                maintenance_environment,
                proof_oid,
                timeout_seconds,
                "PROOF_CLEANUP_FAILED",
            ):
                _raise("PROOF_CLEANUP_FAILED")
            if _proof_database_marker_exists(
                psql,
                maintenance_environment,
                proof_marker,
                timeout_seconds,
                "PROOF_CLEANUP_FAILED",
            ):
                _raise("PROOF_CLEANUP_FAILED")
            if _proof_database_connection_limit_exists(
                psql,
                maintenance_environment,
                proof_connection_limit,
                timeout_seconds,
                "PROOF_CLEANUP_FAILED",
            ):
                _raise("PROOF_CLEANUP_FAILED")
            return
        current_oid, current_owner_oid, current_connection_limit, _current_marker = current_identity
        if (proof_oid is not None and current_oid != proof_oid) or (
            proof_oid is None
            and (
                current_owner_oid != proof_owner_oid
                or current_connection_limit != proof_connection_limit
            )
        ):
            _raise("PROOF_CLEANUP_FAILED")
        _run_command(
            (dropdb, "--no-password", "--if-exists", "--force", proof_database),
            environment=maintenance_environment,
            timeout_seconds=timeout_seconds,
            failure_code="PROOF_CLEANUP_FAILED",
        )
        if _proof_database_exists(
            psql,
            maintenance_environment,
            proof_database,
            timeout_seconds,
            "PROOF_CLEANUP_FAILED",
        ):
            _raise("PROOF_CLEANUP_FAILED")
        if proof_oid is not None and _proof_database_oid_exists(
            psql,
            maintenance_environment,
            proof_oid,
            timeout_seconds,
            "PROOF_CLEANUP_FAILED",
        ):
            _raise("PROOF_CLEANUP_FAILED")
        if _proof_database_marker_exists(
            psql,
            maintenance_environment,
            proof_marker,
            timeout_seconds,
            "PROOF_CLEANUP_FAILED",
        ):
            _raise("PROOF_CLEANUP_FAILED")
        if _proof_database_connection_limit_exists(
            psql,
            maintenance_environment,
            proof_connection_limit,
            timeout_seconds,
            "PROOF_CLEANUP_FAILED",
        ):
            _raise("PROOF_CLEANUP_FAILED")
    except RecoveryError:
        _raise("PROOF_CLEANUP_FAILED")


def _install_deferred_signal_handlers(
    interrupted: list[bool],
) -> dict[signal.Signals, Any]:
    previous: dict[signal.Signals, Any] = {}

    def handler(signum: int, frame: Any) -> None:
        del signum, frame
        interrupted[0] = True

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        previous[signal_name] = signal.getsignal(signal_name)
        signal.signal(signal_name, handler)
    return previous


def _restore_signal_handlers(previous: dict[signal.Signals, Any]) -> None:
    for signal_name, handler in previous.items():
        signal.signal(signal_name, handler)


def _validate_restore_acknowledgements(args: argparse.Namespace, environment: str) -> None:
    if not args.confirm_isolated_restore:
        _raise("RESTORE_GUARD_REJECTED")
    if environment in {"staging", "prod"}:
        if (
            not args.confirm_non_production_target
            or args.change_ticket is None
            or CHANGE_TICKET_PATTERN.fullmatch(args.change_ticket) is None
        ):
            _raise("RESTORE_GUARD_REJECTED")
    elif (
        args.change_ticket is not None
        and CHANGE_TICKET_PATTERN.fullmatch(args.change_ticket) is None
    ):
        _raise("RESTORE_GUARD_REJECTED")


def _restore_proof(args: argparse.Namespace) -> dict[str, Any]:
    timeout_seconds = _timeout(args.timeout_seconds)
    environment_name = _required_environment()
    _validate_restore_acknowledgements(args, environment_name)
    source = _parse_postgres_url(os.environ.get("IK_DATABASE_URL"))
    admin = _parse_postgres_url(os.environ.get("IK_RECOVERY_ADMIN_DATABASE_URL"))
    if source.server_identity != admin.server_identity or source.database == admin.database:
        _raise("RESTORE_GUARD_REJECTED")
    proof_database = _proof_database_name(args.proof_database, source, admin)
    verified = _verify_backup(args.backup_dir, timeout_seconds)
    if verified.manifest["database_name"] != source.database:
        _raise("RESTORE_GUARD_REJECTED")
    if (
        environment_name in {"staging", "prod"}
        and verified.manifest["source_release_commit_sha"] == "development"
    ):
        _raise("RESTORE_GUARD_REJECTED")
    object_configuration = _proof_object_configuration(args, verified)

    psql = _resolve_tool("psql")
    pg_restore = _resolve_tool("pg_restore")
    createdb = _resolve_tool("createdb")
    dropdb = _resolve_tool("dropdb")
    _resolve_tool("alembic")
    mc = _resolve_tool("mc") if object_configuration is not None else None
    _require_tool_help(
        createdb,
        (
            "--encoding",
            "--no-password",
            "--template",
            "DESCRIPTION",
        ),
        timeout_seconds,
    )
    _require_tool_help(
        dropdb,
        ("--force", "--if-exists", "--no-password"),
        timeout_seconds,
    )

    if object_configuration is not None:
        if mc is None:
            _raise("PREREQUISITE_UNAVAILABLE")
        _, _, proof_alias, proof_bucket = object_configuration
        _ensure_proof_bucket_empty(mc, proof_alias, proof_bucket, timeout_seconds)

    started_at = _utc_now()
    monotonic_started = time.monotonic()
    cleanup_required = False
    proof_marker = f"ik-recovery-proof-{secrets.token_hex(16)}"
    proof_connection_limit = 1_000_000_000 + secrets.randbelow(1_000_000_000)
    proof_oid: int | None = None
    proof_owner_oid = 0
    result: dict[str, Any] | None = None
    with _postgres_environment(
        admin,
        database=admin.database,
        timeout_seconds=timeout_seconds,
        additional_databases=(proof_database,),
    ) as maintenance_environment:
        if (
            _psql_output(
                psql,
                maintenance_environment,
                "SELECT 1;",
                timeout_seconds,
                "PROOF_DATABASE_UNAVAILABLE",
            )
            != "1"
        ):
            _raise("PROOF_DATABASE_UNAVAILABLE")
        if (
            _psql_output(
                psql,
                maintenance_environment,
                f"SELECT count(*) FROM pg_catalog.pg_database WHERE datname = '{source.database}';",
                timeout_seconds,
                "PROOF_DATABASE_UNAVAILABLE",
            )
            != "1"
        ):
            _raise("PROOF_DATABASE_UNAVAILABLE")
        if (
            _psql_output(
                psql,
                maintenance_environment,
                "SELECT CASE WHEN active_role.rolcanlogin "
                "AND active_role.rolcreatedb "
                "AND NOT active_role.rolsuper "
                "AND NOT active_role.rolcreaterole "
                "AND NOT active_role.rolreplication "
                "AND NOT active_role.rolbypassrls "
                "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles inherited_role "
                "WHERE inherited_role.oid <> active_role.oid "
                "AND pg_catalog.pg_has_role(active_role.oid, inherited_role.oid, 'MEMBER')) "
                "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_database owned_database "
                "WHERE owned_database.datdba = active_role.oid) "
                "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_tablespace owned_tablespace "
                "WHERE owned_tablespace.spcowner = active_role.oid) "
                "THEN 1 ELSE 0 END "
                "FROM pg_catalog.pg_roles active_role "
                "WHERE active_role.rolname = current_user;",
                timeout_seconds,
                "PROOF_DATABASE_UNAVAILABLE",
            )
            != "1"
        ):
            _raise("PROOF_DATABASE_UNAVAILABLE")
        proof_owner_text = _psql_output(
            psql,
            maintenance_environment,
            "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user;",
            timeout_seconds,
            "PROOF_DATABASE_UNAVAILABLE",
        )
        if not proof_owner_text.isdigit() or int(proof_owner_text) <= 0:
            _raise("PROOF_DATABASE_UNAVAILABLE")
        proof_owner_oid = int(proof_owner_text)
        if _proof_database_exists(
            psql,
            maintenance_environment,
            proof_database,
            timeout_seconds,
            "PROOF_DATABASE_UNAVAILABLE",
        ):
            _raise("RESTORE_GUARD_REJECTED")
        if _proof_database_connection_limit_exists(
            psql,
            maintenance_environment,
            proof_connection_limit,
            timeout_seconds,
            "PROOF_DATABASE_UNAVAILABLE",
        ):
            _raise("PROOF_DATABASE_UNAVAILABLE")

        try:
            cleanup_required = True
            _run_command(
                (
                    createdb,
                    "--no-password",
                    "--template=template0",
                    "--encoding=UTF8",
                    proof_database,
                    proof_marker,
                ),
                environment=maintenance_environment,
                timeout_seconds=timeout_seconds,
                failure_code="PROOF_DATABASE_UNAVAILABLE",
            )
            created_identity = _proof_database_identity(
                psql,
                maintenance_environment,
                proof_database,
                timeout_seconds,
                "PROOF_DATABASE_UNAVAILABLE",
            )
            if (
                created_identity is None
                or created_identity[1] != proof_owner_oid
                or created_identity[2] != -1
                or created_identity[3] != proof_marker
            ):
                _raise("PROOF_DATABASE_UNAVAILABLE")
            proof_oid = created_identity[0]
            _psql_output(
                psql,
                maintenance_environment,
                f'ALTER DATABASE "{proof_database}" CONNECTION LIMIT {proof_connection_limit};',
                timeout_seconds,
                "PROOF_DATABASE_UNAVAILABLE",
            )
            proof_identity = _proof_database_identity(
                psql,
                maintenance_environment,
                proof_database,
                timeout_seconds,
                "PROOF_DATABASE_UNAVAILABLE",
            )
            if (
                proof_identity is None
                or proof_identity[0] != proof_oid
                or proof_identity[1] != proof_owner_oid
                or proof_identity[2] != proof_connection_limit
                or proof_identity[3] != proof_marker
            ):
                _raise("PROOF_DATABASE_UNAVAILABLE")
            proof_environment = dict(maintenance_environment)
            proof_environment["PGDATABASE"] = proof_database
            _run_command(
                (
                    pg_restore,
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                    "--no-password",
                    f"--dbname={proof_database}",
                    str(verified.backup_directory / DATABASE_DUMP_NAME),
                ),
                environment=proof_environment,
                timeout_seconds=timeout_seconds,
                failure_code="RESTORE_COMMAND_FAILED",
            )
            if (
                _psql_output(
                    psql,
                    proof_environment,
                    "SELECT 1;",
                    timeout_seconds,
                    "RESTORE_VALIDATION_FAILED",
                )
                != "1"
            ):
                _raise("RESTORE_VALIDATION_FAILED")
            restored_revisions = _query_revisions(
                psql,
                proof_environment,
                timeout_seconds,
                "RESTORE_VALIDATION_FAILED",
            )
            if restored_revisions != verified.manifest["source_migration_revision_ids"]:
                _raise("RESTORE_VALIDATION_FAILED")
            counts = _psql_output(
                psql,
                proof_environment,
                "SELECT (SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE')::text "
                "|| '|' || (SELECT count(*) FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r','p') "
                "AND c.relrowsecurity)::text;",
                timeout_seconds,
                "RESTORE_VALIDATION_FAILED",
            )
            parts = counts.split("|")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                _raise("RESTORE_VALIDATION_FAILED")
            public_table_count, rls_enabled_count = (int(part) for part in parts)
            if public_table_count < 1 or not 0 <= rls_enabled_count <= public_table_count:
                _raise("RESTORE_VALIDATION_FAILED")

            storage = verified.manifest["object_storage"]
            if object_configuration is not None:
                if mc is None:
                    _raise("PREREQUISITE_UNAVAILABLE")
                _, _, proof_alias, proof_bucket = object_configuration
                object_result = _restore_and_verify_objects(
                    mc,
                    verified,
                    proof_alias,
                    proof_bucket,
                    timeout_seconds,
                )
            elif storage["state"] == "not_applicable":
                object_result = {"object_count": 0, "status": "not_applicable", "total_bytes": 0}
            else:
                object_result = {"object_count": 0, "status": "not_requested", "total_bytes": 0}

            _verify_backup(str(verified.backup_directory), timeout_seconds)
            result = {
                "migration_revision_ids": restored_revisions,
                "object_storage": object_result,
                "public_base_table_count": public_table_count,
                "rls_enabled_table_count": rls_enabled_count,
                "started_at_utc": started_at,
                "status": "restore_proof_succeeded",
            }
        except KeyboardInterrupt:
            _raise("INTERRUPTED")
        finally:
            if cleanup_required:
                _cleanup_proof_database(
                    dropdb,
                    psql,
                    maintenance_environment,
                    proof_database,
                    proof_marker,
                    proof_oid,
                    proof_owner_oid,
                    proof_connection_limit,
                    timeout_seconds,
                )
    if result is None:
        _raise("RESTORE_VALIDATION_FAILED")
    result["completed_at_utc"] = _utc_now()
    result["duration_seconds"] = round(time.monotonic() - monotonic_started, 3)
    return result


def _read_release_manifest(path_value: str) -> dict[str, Any]:
    path = _path_from_argument(path_value)
    result = _lstat_path_without_symlinks(path)
    if (
        not stat.S_ISREG(result.st_mode)
        or result.st_nlink != 1
        or stat.S_IMODE(result.st_mode) & 0o022
    ):
        _raise("RELEASE_MANIFEST_INVALID")
    _assert_owned(result, "RELEASE_MANIFEST_INVALID")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise("RELEASE_MANIFEST_INVALID")
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (
            result.st_dev,
            result.st_ino,
        ) or before.st_size > MAX_RELEASE_MANIFEST_BYTES:
            _raise("RELEASE_MANIFEST_INVALID")
        chunks: list[bytes] = []
        remaining = MAX_RELEASE_MANIFEST_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(data) > MAX_RELEASE_MANIFEST_BYTES
            or before.st_ino != after.st_ino
            or before.st_dev != after.st_dev
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            _raise("RELEASE_MANIFEST_INVALID")
    finally:
        os.close(descriptor)

    value = _parse_json_bytes(data, "RELEASE_MANIFEST_INVALID")
    if type(value) is not dict or set(value) != {
        "app_version",
        "build_timestamp_utc",
        "compatible_migration_head_ids",
        "release_commit_sha",
    }:
        _raise("RELEASE_MANIFEST_INVALID")
    if (
        type(value["release_commit_sha"]) is not str
        or COMMIT_SHA_PATTERN.fullmatch(value["release_commit_sha"]) is None
        or type(value["app_version"]) is not str
        or APP_VERSION_PATTERN.fullmatch(value["app_version"]) is None
    ):
        _raise("RELEASE_MANIFEST_INVALID")
    _validate_utc_timestamp(value["build_timestamp_utc"], "RELEASE_MANIFEST_INVALID")
    _validate_revision_ids(
        value["compatible_migration_head_ids"],
        "RELEASE_MANIFEST_INVALID",
    )
    return value


def _rollback_guard(args: argparse.Namespace) -> dict[str, Any]:
    timeout_seconds = _timeout(args.timeout_seconds)
    _required_environment()
    current = _read_release_manifest(args.current_release_manifest)
    target = _read_release_manifest(args.target_release_manifest)
    if current["release_commit_sha"] == target["release_commit_sha"]:
        _raise("ROLLBACK_GUARD_REJECTED")
    source = _parse_postgres_url(os.environ.get("IK_DATABASE_URL"))
    psql = _resolve_tool("psql")
    _resolve_tool("alembic")
    with _postgres_environment(
        source,
        database=source.database,
        timeout_seconds=timeout_seconds,
    ) as postgres_environment:
        live_revisions = _query_revisions(
            psql,
            postgres_environment,
            timeout_seconds,
            "ROLLBACK_GUARD_REJECTED",
        )
    if (
        live_revisions != current["compatible_migration_head_ids"]
        or live_revisions != target["compatible_migration_head_ids"]
    ):
        _raise("ROLLBACK_GUARD_REJECTED")
    return {"safe_for_application_rollback": True}


def _build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        prog="recovery.py",
        description="Fail-closed production recovery proof tooling.",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=SafeArgumentParser,
    )

    backup = subparsers.add_parser("backup", help="Create and verify a new private backup.")
    backup.add_argument("--output-root", required=True, help="Existing absolute private directory.")
    backup.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    backup.set_defaults(handler=_backup)

    verify = subparsers.add_parser("verify-backup", help="Read-only backup verification.")
    verify.add_argument("--backup-dir", required=True, help="Absolute backup directory.")
    verify.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    verify.set_defaults(handler=_verify_backup_command)

    restore = subparsers.add_parser(
        "restore-proof",
        help="Prove restore into an isolated database.",
    )
    restore.add_argument("--backup-dir", required=True, help="Absolute backup directory.")
    restore.add_argument("--proof-database", required=True)
    restore.add_argument("--confirm-isolated-restore", action="store_true")
    restore.add_argument("--confirm-non-production-target", action="store_true")
    restore.add_argument("--change-ticket")
    restore.add_argument("--include-objects", action="store_true")
    restore.add_argument("--proof-object-alias")
    restore.add_argument("--proof-object-bucket")
    restore.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    restore.set_defaults(handler=_restore_proof)

    rollback = subparsers.add_parser(
        "rollback-guard",
        help="Read-only application rollback compatibility guard.",
    )
    rollback.add_argument("--current-release-manifest", required=True)
    rollback.add_argument("--target-release-manifest", required=True)
    rollback.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    rollback.set_defaults(handler=_rollback_guard)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    os.umask(0o077)
    raw_arguments = list(argv) if argv is not None else sys.argv[1:]
    command = (
        raw_arguments[0]
        if raw_arguments
        and raw_arguments[0]
        in {
            "backup",
            "restore-proof",
            "rollback-guard",
            "verify-backup",
        }
        else None
    )
    try:
        parser = _build_parser()
        args = parser.parse_args(raw_arguments)
        command = args.command
        result = args.handler(args)
        if _write_json(result):
            return 0
        with contextlib.suppress(OSError):
            sys.stderr.write("Recovery operation failed.\n")
        return 1
    except RecoveryError as error:
        if command == "rollback-guard":
            _write_json(
                {
                    "reason_code": error.reason_code,
                    "safe_for_application_rollback": False,
                }
            )
        else:
            _write_json({"reason_code": error.reason_code, "status": "failed"})
        with contextlib.suppress(OSError):
            sys.stderr.write("Recovery operation failed.\n")
        return 1
    except KeyboardInterrupt:
        if command == "rollback-guard":
            _write_json({"reason_code": "INTERRUPTED", "safe_for_application_rollback": False})
        else:
            _write_json({"reason_code": "INTERRUPTED", "status": "failed"})
        with contextlib.suppress(OSError):
            sys.stderr.write("Recovery operation failed.\n")
        return 130
    except Exception:
        if command == "rollback-guard":
            _write_json({"reason_code": "INTERNAL_ERROR", "safe_for_application_rollback": False})
        else:
            _write_json({"reason_code": "INTERNAL_ERROR", "status": "failed"})
        with contextlib.suppress(OSError):
            sys.stderr.write("Recovery operation failed.\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
