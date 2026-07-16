"""Idempotent transaction boundary for employee document-request writes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.document_request import EmployeeDocumentRequestStatus
from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.platform.request_context import RequestContext
from app.schemas.document_request import (
    EmployeeDocumentRequestCreate,
    EmployeeDocumentRequestDecision,
    EmployeeDocumentRequestRead,
)
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.document_request_service import DocumentRequestService


@dataclass(slots=True)
class DocumentRequestCommandHandler:
    service: DocumentRequestService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService

    async def create(
        self,
        *,
        request_context: RequestContext,
        payload: EmployeeDocumentRequestCreate,
        idempotency_key: str | None,
    ) -> EmployeeDocumentRequestRead:
        return await self._execute(
            request_context=request_context,
            idempotency_key=idempotency_key,
            command_name="document_requests.create.v1",
            fingerprint={"payload": payload.model_dump(mode="json")},
            operation=lambda: self.service.create(
                request_context=request_context,
                payload=payload,
            ),
        )

    async def decide(
        self,
        *,
        request_context: RequestContext,
        request_id: UUID,
        decision: EmployeeDocumentRequestStatus,
        payload: EmployeeDocumentRequestDecision,
        idempotency_key: str | None,
    ) -> EmployeeDocumentRequestRead:
        return await self._execute(
            request_context=request_context,
            idempotency_key=idempotency_key,
            command_name=f"document_requests.{decision.value}.v1",
            fingerprint={
                "request_id": str(request_id),
                "payload": payload.model_dump(mode="json"),
            },
            operation=lambda: self.service.decide(
                request_context=request_context,
                request_id=request_id,
                decision=decision,
                payload=payload,
            ),
        )

    async def _execute(
        self,
        *,
        request_context: RequestContext,
        idempotency_key: str | None,
        command_name: str,
        fingerprint: dict[str, object],
        operation,
    ) -> EmployeeDocumentRequestRead:
        tenant_id = request_context.require_tenant().tenant_id
        actor_id = request_context.actor_id
        if actor_id is None:
            raise RuntimeError("Document request command requires an actor")
        return await IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        ).execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name=command_name,
            request_fingerprint=command_fingerprint(
                {
                    "actor_id": str(actor_id),
                    "membership_id": str(request_context.require_membership()),
                    **fingerprint,
                }
            ),
            operation=operation,
            serialize=lambda item: item.model_dump(mode="json"),
            deserialize=EmployeeDocumentRequestRead.model_validate,
        )


__all__ = ["DocumentRequestCommandHandler"]
