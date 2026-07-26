#!/usr/bin/env python3
"""Generate a canonical immutable release manifest without runtime service access."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
UTC_TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
APP_VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
REVISION_PATTERN = re.compile(r"[0-9a-z_]+")
MAX_PATH_BYTES = 4_096
MAX_REPOSITORY_FILE_BYTES = 1_048_576
MANIFEST_KEYS = frozenset(
    {
        "app_version",
        "build_timestamp_utc",
        "compatible_migration_head_ids",
        "release_commit_sha",
    }
)


class ManifestError(Exception):
    """An intentionally generic, machine-readable manifest failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ManifestError("INVALID_ARGUMENT")


def _raise(reason_code: str) -> NoReturn:
    raise ManifestError(reason_code)


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


def _validate_path_text(value: str, *, absolute: bool, reason_code: str) -> tuple[str, ...]:
    if (
        not value
        or len(value.encode("utf-8", "surrogatepass")) > MAX_PATH_BYTES
        or "\\" in value
        or any(ord(character) < 32 or 0x7F <= ord(character) <= 0x9F for character in value)
        or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    ):
        _raise(reason_code)
    if absolute != value.startswith("/") or value == "/":
        _raise(reason_code)
    raw_components = value[1:].split("/") if absolute else value.split("/")
    if any(
        not component or component in {".", ".."} or len(component.encode("utf-8")) > 255
        for component in raw_components
    ):
        _raise(reason_code)
    return tuple(raw_components)


def _absolute_path(value: str, reason_code: str) -> Path:
    components = _validate_path_text(value, absolute=True, reason_code=reason_code)
    return Path("/").joinpath(*components)


def _relative_path(value: str, root: Path, reason_code: str) -> Path:
    components = _validate_path_text(value, absolute=False, reason_code=reason_code)
    return root.joinpath(*components)


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _allowed_directory(result: os.stat_result, *, final: bool, reason_code: str) -> None:
    effective_user = os.geteuid() if hasattr(os, "geteuid") else result.st_uid
    if not stat.S_ISDIR(result.st_mode) or result.st_uid not in {0, effective_user}:
        _raise(reason_code)
    writable_by_others = stat.S_IMODE(result.st_mode) & 0o022
    if final:
        if result.st_uid != effective_user or writable_by_others:
            _raise(reason_code)
    elif writable_by_others and not (
        result.st_uid == 0 and stat.S_IMODE(result.st_mode) & stat.S_ISVTX
    ):
        _raise(reason_code)


def _open_absolute_directory(
    path: Path,
    *,
    create: bool,
    reason_code: str,
) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open("/", _directory_flags())
        components = path.parts[1:]
        for index, component in enumerate(components):
            final = index == len(components) - 1
            try:
                child = os.open(component, _directory_flags(), dir_fd=descriptor)
            except OSError as error:
                if not create or error.errno != errno.ENOENT:
                    _raise(reason_code)
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                    child = os.open(component, _directory_flags(), dir_fd=descriptor)
                except OSError:
                    _raise(reason_code)
            os.close(descriptor)
            descriptor = child
            _allowed_directory(os.fstat(descriptor), final=final, reason_code=reason_code)
        if not components:
            _raise(reason_code)
        result = descriptor
        descriptor = None
        return result
    except ManifestError:
        raise
    except OSError:
        _raise(reason_code)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _repository_root(value: str | None) -> Path:
    if value is None:
        try:
            default = Path(__file__).resolve(strict=True).parents[2]
        except (IndexError, OSError):
            _raise("INVALID_REPOSITORY")
        root = _absolute_path(str(default), "INVALID_REPOSITORY")
    else:
        root = _absolute_path(value, "INVALID_REPOSITORY")
    descriptor = _open_absolute_directory(
        root,
        create=False,
        reason_code="INVALID_REPOSITORY",
    )
    os.close(descriptor)
    return root


def _read_repository_file(path: Path) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise("INVALID_REPOSITORY")
    try:
        before = os.fstat(descriptor)
        effective_user = os.geteuid() if hasattr(os, "geteuid") else before.st_uid
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid not in {0, effective_user}
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_nlink != 1
            or before.st_size > MAX_REPOSITORY_FILE_BYTES
        ):
            _raise("INVALID_REPOSITORY")
        chunks: list[bytes] = []
        remaining = MAX_REPOSITORY_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(data) > MAX_REPOSITORY_FILE_BYTES
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            _raise("INVALID_REPOSITORY")
        return data
    except ManifestError:
        raise
    except OSError:
        _raise("INVALID_REPOSITORY")
    finally:
        os.close(descriptor)


def _app_version(repository_root: Path) -> str:
    data = _read_repository_file(repository_root / "pyproject.toml")
    try:
        document = tomllib.loads(data.decode("utf-8", "strict"))
        project = document["project"]
        version = project["version"]
    except (KeyError, TypeError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        _raise("INVALID_APP_VERSION")
    if type(project) is not dict or type(version) is not str:
        _raise("INVALID_APP_VERSION")
    if APP_VERSION_PATTERN.fullmatch(version) is None:
        _raise("INVALID_APP_VERSION")
    return version


def _config_path(value: str, repository_root: Path) -> Path:
    if value.startswith("/"):
        path = _absolute_path(value, "MIGRATION_DISCOVERY_FAILED")
    else:
        path = _relative_path(value, repository_root, "MIGRATION_DISCOVERY_FAILED")
    try:
        path.relative_to(repository_root)
    except ValueError:
        _raise("MIGRATION_DISCOVERY_FAILED")
    return path


def _migration_heads(repository_root: Path) -> list[str]:
    ini_path = repository_root / "alembic.ini"
    _read_repository_file(ini_path)
    try:
        with (
            open(os.devnull, "w", encoding="utf-8") as discard,
            contextlib.redirect_stdout(discard),
            contextlib.redirect_stderr(discard),
        ):
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            config = Config(str(ini_path), stdout=discard)
            script_location = config.get_main_option("script_location")
            if not script_location:
                _raise("MIGRATION_DISCOVERY_FAILED")
            script_path = _config_path(script_location, repository_root)
            descriptor = _open_absolute_directory(
                script_path,
                create=False,
                reason_code="MIGRATION_DISCOVERY_FAILED",
            )
            os.close(descriptor)
            config.set_main_option("script_location", str(script_path).replace("%", "%%"))
            prepend_sys_path = config.get_main_option("prepend_sys_path")
            if prepend_sys_path:
                prepend_path = _config_path(prepend_sys_path, repository_root)
                descriptor = _open_absolute_directory(
                    prepend_path,
                    create=False,
                    reason_code="MIGRATION_DISCOVERY_FAILED",
                )
                os.close(descriptor)
                config.set_main_option("prepend_sys_path", str(prepend_path).replace("%", "%%"))
            discovered = ScriptDirectory.from_config(config).get_heads()
    except ManifestError:
        raise
    except SystemExit:
        _raise("MIGRATION_DISCOVERY_FAILED")
    except Exception:
        _raise("MIGRATION_DISCOVERY_FAILED")

    if not 1 <= len(discovered) <= 64:
        _raise("INVALID_MIGRATION_HEADS")
    heads: list[str] = []
    for revision in discovered:
        if (
            type(revision) is not str
            or len(revision) > 128
            or REVISION_PATTERN.fullmatch(revision) is None
        ):
            _raise("INVALID_MIGRATION_HEADS")
        heads.append(revision)
    if len(heads) != len(set(heads)):
        _raise("INVALID_MIGRATION_HEADS")
    return sorted(heads)


def _validate_commit_sha(value: str) -> str:
    if COMMIT_SHA_PATTERN.fullmatch(value) is None:
        _raise("INVALID_COMMIT_SHA")
    return value


def _validate_build_timestamp(value: str) -> str:
    if UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        _raise("INVALID_BUILD_TIMESTAMP")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    except ValueError:
        _raise("INVALID_BUILD_TIMESTAMP")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _raise("INVALID_BUILD_TIMESTAMP")
    return value


def _output_path(value: str, repository_root: Path) -> Path:
    if value.startswith("/"):
        return _absolute_path(value, "UNSAFE_OUTPUT")
    return _relative_path(value, repository_root, "UNSAFE_OUTPUT")


def _existing_target_identity(directory_fd: int, name: str) -> tuple[int, int] | None:
    try:
        result = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError:
        _raise("UNSAFE_OUTPUT")
    effective_user = os.geteuid() if hasattr(os, "geteuid") else result.st_uid
    if (
        not stat.S_ISREG(result.st_mode)
        or result.st_uid != effective_user
        or stat.S_IMODE(result.st_mode) & 0o022
        or result.st_nlink != 1
    ):
        _raise("UNSAFE_OUTPUT")
    return (result.st_dev, result.st_ino)


def _assert_target_unchanged(
    directory_fd: int,
    name: str,
    identity: tuple[int, int] | None,
) -> None:
    current = _existing_target_identity(directory_fd, name)
    if current != identity:
        _raise("UNSAFE_OUTPUT")


def _atomic_write(
    directory_fd: int,
    name: str,
    data: bytes,
    previous_identity: tuple[int, int] | None,
) -> None:
    temporary_name = f".release-manifest-{secrets.token_hex(12)}.tmp"
    descriptor: int | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _raise("WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        _assert_target_unchanged(directory_fd, name, previous_identity)
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except ManifestError:
        raise
    except OSError:
        _raise("WRITE_FAILED")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with contextlib.suppress(OSError):
            os.unlink(temporary_name, dir_fd=directory_fd)


def _verify_file(directory_fd: int, name: str, expected: bytes) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError:
        _raise("WRITE_FAILED")
    try:
        result = os.fstat(descriptor)
        effective_user = os.geteuid() if hasattr(os, "geteuid") else result.st_uid
        if (
            not stat.S_ISREG(result.st_mode)
            or result.st_uid != effective_user
            or stat.S_IMODE(result.st_mode) != 0o600
            or result.st_nlink != 1
            or result.st_size != len(expected)
        ):
            _raise("WRITE_FAILED")
        data = b""
        while len(data) <= len(expected):
            chunk = os.read(descriptor, len(expected) + 1 - len(data))
            if not chunk:
                break
            data += chunk
        if data != expected:
            _raise("WRITE_FAILED")
    except ManifestError:
        raise
    except OSError:
        _raise("WRITE_FAILED")
    finally:
        os.close(descriptor)


def _write_manifest(output: Path, manifest_data: bytes) -> str:
    checksum_name = f"{output.name}.sha256"
    if len(checksum_name.encode("utf-8")) > 255:
        _raise("UNSAFE_OUTPUT")
    digest = hashlib.sha256(manifest_data).hexdigest()
    try:
        checksum_data = f"{digest}  {output.name}\n".encode("utf-8", "strict")
    except UnicodeEncodeError:
        _raise("UNSAFE_OUTPUT")

    directory_fd = _open_absolute_directory(
        output.parent,
        create=True,
        reason_code="UNSAFE_OUTPUT",
    )
    try:
        manifest_identity = _existing_target_identity(directory_fd, output.name)
        checksum_identity = _existing_target_identity(directory_fd, checksum_name)
        _atomic_write(directory_fd, output.name, manifest_data, manifest_identity)
        _atomic_write(directory_fd, checksum_name, checksum_data, checksum_identity)
        _verify_file(directory_fd, output.name, manifest_data)
        _verify_file(directory_fd, checksum_name, checksum_data)
    finally:
        os.close(directory_fd)
    return digest


def _build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        prog="release_manifest.py",
        description="Generate a canonical immutable release manifest.",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--build-timestamp", required=True)
    parser.add_argument(
        "--repository-root",
        help="Absolute repository root; defaults from this script's location.",
    )
    return parser


def _generate(args: argparse.Namespace) -> dict[str, Any]:
    commit_sha = _validate_commit_sha(args.commit_sha)
    build_timestamp = _validate_build_timestamp(args.build_timestamp)
    repository_root = _repository_root(args.repository_root)
    output = _output_path(args.output, repository_root)
    app_version = _app_version(repository_root)
    migration_heads = _migration_heads(repository_root)
    manifest = {
        "app_version": app_version,
        "build_timestamp_utc": build_timestamp,
        "compatible_migration_head_ids": migration_heads,
        "release_commit_sha": commit_sha,
    }
    if set(manifest) != MANIFEST_KEYS:
        _raise("INTERNAL_ERROR")
    manifest_data = _canonical_json(manifest)
    digest = _write_manifest(output, manifest_data)
    return {
        "app_version": app_version,
        "build_timestamp_utc": build_timestamp,
        "compatible_migration_head_ids": migration_heads,
        "manifest_basename": output.name,
        "manifest_sha256": digest,
        "release_commit_sha": commit_sha,
        "status": "succeeded",
    }


def main(argv: Sequence[str] | None = None) -> int:
    os.umask(0o077)
    try:
        args = _build_parser().parse_args(list(argv) if argv is not None else None)
        result = _generate(args)
        if _write_json(result):
            return 0
        with contextlib.suppress(OSError):
            sys.stderr.write("Release manifest generation failed.\n")
        return 1
    except ManifestError as error:
        _write_json({"reason_code": error.reason_code, "status": "failed"})
        with contextlib.suppress(OSError):
            sys.stderr.write("Release manifest generation failed.\n")
        return 1
    except KeyboardInterrupt:
        _write_json({"reason_code": "INTERRUPTED", "status": "failed"})
        with contextlib.suppress(OSError):
            sys.stderr.write("Release manifest generation failed.\n")
        return 130
    except Exception:
        _write_json({"reason_code": "INTERNAL_ERROR", "status": "failed"})
        with contextlib.suppress(OSError):
            sys.stderr.write("Release manifest generation failed.\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
