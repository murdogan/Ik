"""SQLAlchemy adapter for tenant-scoped command idempotency receipts."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_idempotency import CommandIdempotency
from app.platform.db import UnitOfWork, constraint_name_from_error
from app.platform.idempotency import (
    IdempotencyKeyMismatchError,
    IdempotencyReplay,
    IdempotencyReplayUnavailableError,
)

IDEMPOTENCY_KEY_UNIQUE_CONSTRAINT = "uq_command_idempotency_tenant_key"
_SQLITE_IDEMPOTENCY_UNIQUE_SIGNATURE = (
    "UNIQUE constraint failed: command_idempotency.tenant_id, "
    "command_idempotency.idempotency_key"
)


class _CommandResult(Protocol):
    id: UUID


_ResultT = TypeVar("_ResultT", bound=_CommandResult)


class _ConcurrentIdempotencyClaimError(Exception):
    """Internal signal raised after the database chooses the winning key claimant."""


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    receipt: CommandIdempotency | None = None
    replay: IdempotencyReplay | None = None


class CommandIdempotencyService:
    """Claim and complete a key in the same transaction as its domain write."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def begin(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
        command_name: str,
        request_fingerprint: str,
    ) -> IdempotencyClaim:
        existing = await self._find(tenant_id, idempotency_key)
        if existing is not None:
            return IdempotencyClaim(
                replay=_validated_replay(
                    existing,
                    command_name=command_name,
                    request_fingerprint=request_fingerprint,
                )
            )

        receipt = CommandIdempotency(
            id=uuid4(),
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name=command_name,
            request_fingerprint=request_fingerprint,
        )
        self.session.add(receipt)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if _is_idempotency_unique_violation(exc):
                raise _ConcurrentIdempotencyClaimError from exc
            raise
        return IdempotencyClaim(receipt=receipt)

    async def complete(
        self,
        claim: IdempotencyClaim,
        *,
        resource_id: UUID,
        response_payload: dict[str, object],
    ) -> None:
        if claim.receipt is None or claim.replay is not None:
            raise RuntimeError("Only a new idempotency claim can be completed")
        claim.receipt.resource_id = resource_id
        claim.receipt.response_payload = response_payload
        claim.receipt.completed_at = datetime.now(UTC)
        await self.session.flush()

    async def replay(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
        command_name: str,
        request_fingerprint: str,
    ) -> IdempotencyReplay:
        receipt = await self._find(tenant_id, idempotency_key)
        if receipt is None:
            raise IdempotencyReplayUnavailableError
        return _validated_replay(
            receipt,
            command_name=command_name,
            request_fingerprint=request_fingerprint,
        )

    async def _find(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> CommandIdempotency | None:
        return await self.session.scalar(
            select(CommandIdempotency)
            .where(CommandIdempotency.tenant_id == tenant_id)
            .where(CommandIdempotency.idempotency_key == idempotency_key)
        )


@dataclass(slots=True)
class IdempotentCommandExecutor:
    """Wrap one command with a durable receipt and optional transactional precondition."""

    service: CommandIdempotencyService
    unit_of_work: UnitOfWork

    async def execute(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str | None,
        command_name: str,
        request_fingerprint: str,
        precondition: Callable[[], Awaitable[None]] | None = None,
        operation: Callable[[], Awaitable[_ResultT]],
        serialize: Callable[[_ResultT], dict[str, object]],
        deserialize: Callable[[dict[str, object]], _ResultT],
    ) -> _ResultT:
        if idempotency_key is None:

            async def execute_unkeyed_command() -> _ResultT:
                if precondition is not None:
                    await precondition()
                return await operation()

            return await self.unit_of_work.execute(execute_unkeyed_command)

        async def execute_claimed_command() -> _ResultT:
            if precondition is not None:
                await precondition()
            claim = await self.service.begin(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command_name=command_name,
                request_fingerprint=request_fingerprint,
            )
            if claim.replay is not None:
                return deserialize(claim.replay.response_payload)

            result = await operation()
            await self.service.complete(
                claim,
                resource_id=result.id,
                response_payload=serialize(result),
            )
            return result

        try:
            return await self.unit_of_work.execute(execute_claimed_command)
        except _ConcurrentIdempotencyClaimError:

            async def replay_claimed_command() -> IdempotencyReplay:
                if precondition is not None:
                    await precondition()
                return await self.service.replay(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    command_name=command_name,
                    request_fingerprint=request_fingerprint,
                )

            replay = await self.unit_of_work.execute(replay_claimed_command)
            return deserialize(replay.response_payload)


def _validated_replay(
    receipt: CommandIdempotency,
    *,
    command_name: str,
    request_fingerprint: str,
) -> IdempotencyReplay:
    if (
        receipt.command_name != command_name
        or receipt.request_fingerprint != request_fingerprint
    ):
        raise IdempotencyKeyMismatchError
    if (
        receipt.resource_id is None
        or receipt.response_payload is None
        or receipt.completed_at is None
    ):
        raise IdempotencyReplayUnavailableError
    return IdempotencyReplay(
        resource_id=receipt.resource_id,
        response_payload=dict(receipt.response_payload),
    )


def _is_idempotency_unique_violation(exc: IntegrityError) -> bool:
    if constraint_name_from_error(exc) == IDEMPOTENCY_KEY_UNIQUE_CONSTRAINT:
        return True
    return _SQLITE_IDEMPOTENCY_UNIQUE_SIGNATURE in str(exc.orig)
