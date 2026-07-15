"""Malware scanning port plus ClamAV and controlled local adapters."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class MalwareScanVerdict(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"


@dataclass(frozen=True, slots=True)
class MalwareScanOutcome:
    verdict: MalwareScanVerdict
    provider: str
    version: str | None = None


class MalwareScanError(RuntimeError):
    """Safe scanner failure without provider payload or malware content."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class MalwareScanner(Protocol):
    async def scan(self, path: Path) -> MalwareScanOutcome: ...


class LocalCleanMalwareScanner:
    """Explicit local/dev-only adapter; production configuration rejects it."""

    async def scan(self, path: Path) -> MalwareScanOutcome:
        if not path.is_file():
            raise MalwareScanError("input_unavailable")
        return MalwareScanOutcome(
            verdict=MalwareScanVerdict.CLEAN,
            provider="local_clean",
            version=None,
        )


class ClamAVMalwareScanner:
    _CHUNK_SIZE = 128 * 1024
    _MAX_RESPONSE_BYTES = 2048

    def __init__(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: float,
        scan_timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._connect_timeout_seconds = connect_timeout_seconds
        self._scan_timeout_seconds = scan_timeout_seconds

    async def scan(self, path: Path) -> MalwareScanOutcome:
        if not path.is_file():
            raise MalwareScanError("input_unavailable")
        try:
            async with asyncio.timeout(self._scan_timeout_seconds):
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self._host,
                        self._port,
                        limit=self._MAX_RESPONSE_BYTES,
                    ),
                    timeout=self._connect_timeout_seconds,
                )
                try:
                    writer.write(b"zINSTREAM\0")
                    with path.open("rb") as file_handle:
                        while chunk := await asyncio.to_thread(
                            file_handle.read,
                            self._CHUNK_SIZE,
                        ):
                            writer.write(len(chunk).to_bytes(4, "big"))
                            writer.write(chunk)
                            await writer.drain()
                    writer.write(b"\x00\x00\x00\x00")
                    await writer.drain()
                    response = await reader.readuntil(b"\0")
                finally:
                    writer.close()
                    await writer.wait_closed()
        except TimeoutError as exc:
            raise MalwareScanError("scanner_timeout") from exc
        except (
            ConnectionError,
            OSError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ) as exc:
            raise MalwareScanError("scanner_unavailable") from exc

        if response.endswith(b" OK\0"):
            return MalwareScanOutcome(
                verdict=MalwareScanVerdict.CLEAN,
                provider="clamav",
            )
        if response.endswith(b" FOUND\0"):
            return MalwareScanOutcome(
                verdict=MalwareScanVerdict.INFECTED,
                provider="clamav",
            )
        raise MalwareScanError("scanner_protocol_error")


__all__ = [
    "ClamAVMalwareScanner",
    "LocalCleanMalwareScanner",
    "MalwareScanError",
    "MalwareScanOutcome",
    "MalwareScanner",
    "MalwareScanVerdict",
]
