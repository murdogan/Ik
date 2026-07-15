"""Atomic and idempotent Phase 6 leave command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.platform.request_context import RequestContext
from app.schemas.leave import (
    LeaveAdjustmentCreate,
    LeaveLedgerEntryRead,
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestRead,
)
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.leave_service import LeaveService


@dataclass(slots=True)
class LeaveCommandHandler:
    service: LeaveService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService

    async def create_request(
        self,
        *,
        request_context: RequestContext,
        payload: LeaveRequestCreate,
        permissions: tuple[str, ...],
        idempotency_key: str | None,
    ) -> LeaveRequestRead:
        tenant_id = request_context.require_tenant().tenant_id
        return await self._execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name="leave_requests.create.v2",
            fingerprint={
                **_actor_fingerprint(request_context),
                "payload": payload.model_dump(mode="json"),
            },
            operation=lambda: self.service.create_request(
                request_context=request_context,
                payload=payload,
                permissions=permissions,
            ),
            serialize=lambda item: item.model_dump(mode="json"),
            deserialize=LeaveRequestRead.model_validate,
        )

    async def decide_request(
        self,
        *,
        request_context: RequestContext,
        request_id: UUID,
        action: str,
        payload: LeaveRequestDecision,
        permissions: tuple[str, ...],
        idempotency_key: str | None,
    ) -> LeaveRequestRead:
        tenant_id = request_context.require_tenant().tenant_id
        return await self._execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name=f"leave_requests.{action}.v2",
            fingerprint={
                **_actor_fingerprint(request_context),
                "request_id": str(request_id),
                "payload": payload.model_dump(mode="json"),
            },
            operation=lambda: self.service.decide_request(
                request_context=request_context,
                request_id=request_id,
                action=action,
                payload=payload,
                permissions=permissions,
            ),
            serialize=lambda item: item.model_dump(mode="json"),
            deserialize=LeaveRequestRead.model_validate,
        )

    async def create_adjustment(
        self,
        *,
        request_context: RequestContext,
        payload: LeaveAdjustmentCreate,
        idempotency_key: str | None,
    ) -> LeaveLedgerEntryRead:
        tenant_id = request_context.require_tenant().tenant_id
        return await self._execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name="leave_adjustments.create.v1",
            fingerprint={
                **_actor_fingerprint(request_context),
                "payload": payload.model_dump(mode="json"),
            },
            operation=lambda: self.service.create_adjustment(
                request_context=request_context,
                payload=payload,
            ),
            serialize=lambda item: item.model_dump(mode="json"),
            deserialize=LeaveLedgerEntryRead.model_validate,
        )

    async def _execute(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str | None,
        command_name: str,
        fingerprint: dict[str, object],
        operation: Callable[[], Awaitable[LeaveRequestRead | LeaveLedgerEntryRead]],
        serialize: Callable[[object], dict[str, object]],
        deserialize: Callable[[dict[str, object]], LeaveRequestRead | LeaveLedgerEntryRead],
    ) -> LeaveRequestRead | LeaveLedgerEntryRead:
        return await IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        ).execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name=command_name,
            request_fingerprint=command_fingerprint(fingerprint),
            operation=operation,
            serialize=serialize,
            deserialize=deserialize,
        )


def _actor_fingerprint(request_context: RequestContext) -> dict[str, object]:
    if request_context.actor_id is None:
        raise RuntimeError("Authenticated leave command requires an actor")
    return {
        "actor_id": str(request_context.actor_id),
        "membership_id": str(request_context.require_membership()),
    }


__all__ = ["LeaveCommandHandler"]
