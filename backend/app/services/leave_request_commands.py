"""Leave-request write orchestration during the modular-monolith migration."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from app.models.leave_request import LeaveRequest
from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.schemas.leave_request import (
    LeaveRequestCreate,
    LeaveRequestDecision,
    LeaveRequestRead,
)
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.leave_request_service import LeaveRequestService


@dataclass(slots=True)
class LeaveRequestCommandHandler:
    service: LeaveRequestService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService | None = None

    async def create_leave_request(
        self,
        tenant_id: UUID,
        payload: LeaveRequestCreate,
        idempotency_key: str | None = None,
    ) -> LeaveRequest | LeaveRequestRead:
        if idempotency_key is None:
            return await self.unit_of_work.execute(
                lambda: self.service.create_leave_request(tenant_id, payload)
            )
        return await self._idempotent_executor().execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name="leave_requests.create",
            request_fingerprint=command_fingerprint(
                {"payload": payload.model_dump(mode="json")}
            ),
            operation=lambda: self.service.create_leave_request(tenant_id, payload),
            serialize=_leave_request_response_payload,
            deserialize=LeaveRequestRead.model_validate,
        )

    async def approve_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
        idempotency_key: str | None = None,
    ) -> LeaveRequest | LeaveRequestRead:
        return await self._execute_decision(
            tenant_id=tenant_id,
            leave_request_id=leave_request_id,
            payload=payload,
            idempotency_key=idempotency_key,
            command_name="leave_requests.approve",
            operation=lambda: self.service.approve_leave_request(
                tenant_id,
                leave_request_id,
                payload,
            ),
        )

    async def reject_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
        idempotency_key: str | None = None,
    ) -> LeaveRequest | LeaveRequestRead:
        return await self._execute_decision(
            tenant_id=tenant_id,
            leave_request_id=leave_request_id,
            payload=payload,
            idempotency_key=idempotency_key,
            command_name="leave_requests.reject",
            operation=lambda: self.service.reject_leave_request(
                tenant_id,
                leave_request_id,
                payload,
            ),
        )

    async def cancel_leave_request(
        self,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
        idempotency_key: str | None = None,
    ) -> LeaveRequest | LeaveRequestRead:
        return await self._execute_decision(
            tenant_id=tenant_id,
            leave_request_id=leave_request_id,
            payload=payload,
            idempotency_key=idempotency_key,
            command_name="leave_requests.cancel",
            operation=lambda: self.service.cancel_leave_request(
                tenant_id,
                leave_request_id,
                payload,
            ),
        )

    async def _execute_decision(
        self,
        *,
        tenant_id: UUID,
        leave_request_id: UUID,
        payload: LeaveRequestDecision,
        idempotency_key: str | None,
        command_name: str,
        operation: Callable[[], Awaitable[LeaveRequest]],
    ) -> LeaveRequest | LeaveRequestRead:
        if idempotency_key is None:
            return await self.unit_of_work.execute(operation)
        return await self._idempotent_executor().execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name=command_name,
            request_fingerprint=command_fingerprint(
                {
                    "leave_request_id": str(leave_request_id),
                    "payload": payload.model_dump(mode="json"),
                }
            ),
            operation=operation,
            serialize=_leave_request_response_payload,
            deserialize=LeaveRequestRead.model_validate,
        )

    def _idempotent_executor(self) -> IdempotentCommandExecutor:
        if self.idempotency is None:
            raise RuntimeError("Idempotency service is required when a key is supplied")
        return IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        )


def _leave_request_response_payload(
    leave_request: LeaveRequest | LeaveRequestRead,
) -> dict[str, object]:
    return LeaveRequestRead.model_validate(leave_request).model_dump(mode="json")
