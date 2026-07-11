"""Argon2id password hashing behind a small credential-safe adapter."""

import asyncio
from collections.abc import Callable
from typing import TypeVar

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$KWUgs9fc2rHDp5IKqPeS1g$"
    "+4kOpxwq+chQh+04KlbNKDw9ItO+kLEVzTp99U8IJB8"
)
_ResultT = TypeVar("_ResultT")


class PasswordManager:
    """Hash and verify passwords without exposing library errors or credential values."""

    def __init__(self, *, max_concurrent_operations: int = 2) -> None:
        if not 1 <= max_concurrent_operations <= 8:
            raise ValueError("Argon2 concurrency must be between 1 and 8")
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._operation_limit = asyncio.Semaphore(max_concurrent_operations)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, encoded_hash: str | None) -> bool:
        candidate_hash = encoded_hash or _DUMMY_PASSWORD_HASH
        try:
            verified = self._hasher.verify(candidate_hash, password)
        except (InvalidHashError, VerificationError):
            return False
        return bool(verified and encoded_hash is not None)

    def needs_rehash(self, encoded_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(encoded_hash)
        except InvalidHashError:
            return False

    async def hash_async(self, password: str) -> str:
        return await self._run_bounded(self.hash, password)

    async def verify_async(self, password: str, encoded_hash: str | None) -> bool:
        return await self._run_bounded(self.verify, password, encoded_hash)

    async def _run_bounded(
        self,
        operation: Callable[..., _ResultT],
        *args: object,
    ) -> _ResultT:
        await self._operation_limit.acquire()
        try:
            future = asyncio.get_running_loop().run_in_executor(None, operation, *args)
        except BaseException:
            self._operation_limit.release()
            raise

        # Cancellation of an HTTP request must not release the permit while its native Argon2
        # worker continues. The completion callback owns the permit independently of the waiter.
        future.add_done_callback(self._release_completed_operation)
        return await asyncio.shield(future)

    def _release_completed_operation(self, future: asyncio.Future[object]) -> None:
        # Retrieve failures even when a cancelled request no longer awaits the executor future.
        try:
            if not future.cancelled():
                future.exception()
        finally:
            self._operation_limit.release()


__all__ = ["PasswordManager"]
