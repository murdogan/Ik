"""Employee write orchestration during the modular-monolith migration."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.models.employee import Employee
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditRecorder,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.platform.request_context import RequestContext
from app.schemas.employee import (
    EmployeeArchive,
    EmployeeCreate,
    EmployeeLifecycleRead,
    EmployeeLifecycleTransition,
    EmployeeRead,
    EmployeeUpdate,
)
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.employee_projection_contract import enforce_response_contract
from app.services.employee_service import EmployeeReadProjection, EmployeeService


@dataclass(slots=True)
class EmployeeCommandHandler:
    service: EmployeeService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService | None = None
    audit_recorder: AuditRecorder | None = None

    async def create_employee(
        self,
        tenant_id: UUID,
        payload: EmployeeCreate,
        idempotency_key: str | None = None,
        request_context: RequestContext | None = None,
    ) -> Employee | EmployeeRead:
        async def operation() -> Employee:
            employee = await self.service.create_employee(tenant_id, payload)
            await self._record_event(
                employee_id=employee.id,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_CREATED,
                action="create",
                changed_fields=_employee_create_changed_fields(payload),
            )
            return employee

        if idempotency_key is None:
            return await self.unit_of_work.execute(operation)
        executor = self._idempotent_executor()
        return await executor.execute(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command_name="employees.create",
            request_fingerprint=command_fingerprint(
                {"payload": payload.model_dump(mode="json")}
            ),
            operation=operation,
            serialize=_employee_response_payload,
            deserialize=EmployeeRead.model_validate,
        )

    async def update_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeUpdate,
        request_context: RequestContext | None = None,
    ) -> EmployeeReadProjection:
        async def operation() -> EmployeeReadProjection:
            employee = await self.service.get_employee(tenant_id, employee_id)
            candidate_fields = tuple(
                field_name
                for field_name in EmployeeUpdate.model_fields
                if field_name in payload.model_fields_set and field_name != "version"
            )
            before = {
                field_name: getattr(employee, field_name)
                for field_name in candidate_fields
            }
            employee = await self.service.update_employee(tenant_id, employee_id, payload)
            changed_fields = tuple(
                sorted(
                    field_name
                    for field_name, before_value in before.items()
                    if getattr(employee, field_name) != before_value
                )
            )
            if changed_fields:
                await self._record_event(
                    employee_id=employee_id,
                    request_context=request_context,
                    event_type=AuditEventType.EMPLOYEE_UPDATED,
                    action="update",
                    changed_fields=changed_fields,
                )
            return await self.service.get_employee_read(tenant_id, employee_id)

        return await self.unit_of_work.execute(operation)

    async def transition_employee_lifecycle(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeLifecycleTransition,
        request_context: RequestContext | None = None,
    ) -> EmployeeLifecycleRead:
        async def operation() -> EmployeeLifecycleRead:
            mutation = await self.service.transition_employee_lifecycle(
                tenant_id,
                employee_id,
                payload,
            )
            if mutation.changed_fields:
                metadata: dict[str, object] = {
                    "before_status": mutation.before_status,
                    "after_status": mutation.employee.status,
                    "assignment_closed": mutation.assignment_closed,
                    "membership_deactivated": mutation.membership_deactivated,
                    "sessions_revoked": mutation.sessions_revoked,
                }
                if mutation.employee.termination_reason is not None:
                    metadata["reason_code"] = mutation.employee.termination_reason
                await self._record_event(
                    employee_id=employee_id,
                    request_context=request_context,
                    event_type=AuditEventType.EMPLOYEE_LIFECYCLE_CHANGED,
                    action="transition_lifecycle",
                    changed_fields=mutation.changed_fields,
                    metadata=metadata,
                )
                if mutation.sessions_revoked and mutation.membership_id is not None:
                    await self._record_session_revocation(
                        membership_id=mutation.membership_id,
                        request_context=request_context,
                    )
            response = EmployeeLifecycleRead.model_validate(mutation.employee)
            enforce_response_contract(response)
            return response

        return await self.unit_of_work.execute(operation)

    async def archive_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        payload: EmployeeArchive,
        request_context: RequestContext | None = None,
    ) -> EmployeeLifecycleRead:
        async def operation() -> EmployeeLifecycleRead:
            mutation = await self.service.archive_employee(
                tenant_id,
                employee_id,
                expected_version=payload.expected_version,
            )
            if mutation.archived:
                await self._record_event(
                    employee_id=employee_id,
                    request_context=request_context,
                    event_type=AuditEventType.EMPLOYEE_ARCHIVED,
                    action="archive",
                    changed_fields=("archived_at",),
                )
            response = EmployeeLifecycleRead.model_validate(mutation.employee)
            enforce_response_contract(response)
            return response

        return await self.unit_of_work.execute(operation)

    async def delete_employee(
        self,
        tenant_id: UUID,
        employee_id: UUID,
        request_context: RequestContext | None = None,
    ) -> None:
        async def operation() -> None:
            mutation = await self.service.archive_employee(tenant_id, employee_id)
            if mutation.archived:
                await self._record_event(
                    employee_id=employee_id,
                    request_context=request_context,
                    event_type=AuditEventType.EMPLOYEE_ARCHIVED,
                    action="archive",
                    changed_fields=("archived_at",),
                )

        await self.unit_of_work.execute(operation)

    def _idempotent_executor(self) -> IdempotentCommandExecutor:
        if self.idempotency is None:
            raise RuntimeError("Idempotency service is required when a key is supplied")
        return IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        )

    async def _record_event(
        self,
        *,
        employee_id: UUID,
        request_context: RequestContext | None,
        event_type: AuditEventType,
        action: str,
        changed_fields: tuple[str, ...],
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if (
            self.audit_recorder is None
            or request_context is None
            or request_context.actor_id is None
        ):
            return
        await self.audit_recorder.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=request_context.actor_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="employee",
                resource_id=employee_id,
                action=action,
                context=AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                changed_fields=changed_fields,
                metadata=metadata or {},
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )

    async def _record_session_revocation(
        self,
        *,
        membership_id: UUID,
        request_context: RequestContext | None,
    ) -> None:
        if (
            self.audit_recorder is None
            or request_context is None
            or request_context.actor_id is None
        ):
            return
        await self.audit_recorder.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=request_context.actor_id,
                event_type=AuditEventType.SESSION_REVOKED,
                category=AuditCategory.TENANT_SECURITY,
                resource_type="tenant_membership",
                resource_id=membership_id,
                action="revoke",
                context=AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                metadata={
                    "revocation_reason": "employee_termination",
                    "source": "employee_lifecycle",
                },
                data_classification=AuditDataClassification.SECURITY_METADATA,
                visibility_class=AuditVisibilityClass.TENANT_SECURITY,
            )
        )


def _employee_create_changed_fields(payload: EmployeeCreate) -> tuple[str, ...]:
    fields = {
        "employee_number",
        "first_name",
        "last_name",
        "status",
        "employment_start_date",
    }
    fields.update(
        field_name
        for field_name in ("email", "department", "position", "employment_end_date")
        if getattr(payload, field_name) is not None
    )
    return tuple(sorted(fields))


def _employee_response_payload(employee: Employee | EmployeeRead) -> dict[str, object]:
    return EmployeeRead.model_validate(employee).model_dump(mode="json")
