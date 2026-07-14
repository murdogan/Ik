"""Atomic P4E workflow commands with value-free audit metadata."""

from dataclasses import dataclass
from uuid import UUID, uuid4

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
from app.platform.db import (
    DatabaseCommandContext,
    DatabaseCommandIntent,
    PersistenceIntegrityError,
    UnitOfWork,
    configure_database_command_context,
)
from app.platform.request_context import RequestContext
from app.schemas.employee_profile_change_request import (
    EmployeeProfileChangeRequestCreate,
    EmployeeProfileChangeRequestExpectedVersion,
    EmployeeProfileChangeRequestHrDetailRead,
    EmployeeProfileChangeRequestReject,
    OwnEmployeeProfileChangeRequestRead,
)
from app.services.employee_profile_change_request_service import (
    ACTIVE_PROFILE_CHANGE_REQUEST_CONSTRAINT,
    EmployeeProfileChangeRequestConflictError,
    EmployeeProfileChangeRequestMutation,
    EmployeeProfileChangeRequestService,
)


@dataclass(slots=True)
class EmployeeProfileChangeRequestCommandHandler:
    service: EmployeeProfileChangeRequestService
    unit_of_work: UnitOfWork
    audit_recorder: AuditRecorder

    async def submit_own(
        self,
        payload: EmployeeProfileChangeRequestCreate,
        *,
        request_context: RequestContext,
    ) -> OwnEmployeeProfileChangeRequestRead:
        tenant_id, membership_id, actor_user_id = _own_context(request_context)
        request_id = uuid4()
        self._configure_database_command(
            intent=DatabaseCommandIntent.P4E_SUBMIT,
            target_id=request_id,
            request_context=request_context,
        )

        async def operation() -> OwnEmployeeProfileChangeRequestRead:
            mutation = await self.service.submit_own(
                request_id=request_id,
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                payload=payload,
            )
            await self._record_event(
                mutation,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_SUBMITTED,
                action="submit_profile_change_request",
                reason_code="employee_submitted",
            )
            if not isinstance(mutation.response, OwnEmployeeProfileChangeRequestRead):
                raise RuntimeError("Own submit returned an HR response")
            return mutation.response

        try:
            return await self.unit_of_work.execute(operation)
        except PersistenceIntegrityError as exc:
            if exc.constraint_name == ACTIVE_PROFILE_CHANGE_REQUEST_CONSTRAINT:
                raise EmployeeProfileChangeRequestConflictError from exc
            raise

    async def cancel_own(
        self,
        request_id: UUID,
        payload: EmployeeProfileChangeRequestExpectedVersion,
        *,
        request_context: RequestContext,
    ) -> OwnEmployeeProfileChangeRequestRead:
        tenant_id, membership_id, actor_user_id = _own_context(request_context)
        self._configure_database_command(
            intent=DatabaseCommandIntent.P4E_CANCEL,
            target_id=request_id,
            request_context=request_context,
        )

        async def operation() -> OwnEmployeeProfileChangeRequestRead:
            mutation = await self.service.cancel_own(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                request_id=request_id,
                payload=payload,
            )
            await self._record_event(
                mutation,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_CANCELLED,
                action="cancel_profile_change_request",
                reason_code="employee_cancelled",
            )
            if not isinstance(mutation.response, OwnEmployeeProfileChangeRequestRead):
                raise RuntimeError("Own cancellation returned an HR response")
            return mutation.response

        return await self.unit_of_work.execute(operation)

    async def approve(
        self,
        request_id: UUID,
        payload: EmployeeProfileChangeRequestExpectedVersion,
        *,
        request_context: RequestContext,
        granted_permissions: tuple[str, ...],
    ) -> EmployeeProfileChangeRequestHrDetailRead:
        tenant_id, membership_id, actor_user_id = _own_context(request_context)
        self._configure_database_command(
            intent=DatabaseCommandIntent.P4E_APPROVE,
            target_id=request_id,
            request_context=request_context,
        )

        async def operation() -> EmployeeProfileChangeRequestHrDetailRead:
            mutation = await self.service.approve(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                granted_permissions=granted_permissions,
                request_id=request_id,
                payload=payload,
            )
            await self._record_event(
                mutation,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_APPROVED,
                action="approve_profile_change_request",
                reason_code="hr_approved",
            )
            if not isinstance(mutation.response, EmployeeProfileChangeRequestHrDetailRead):
                raise RuntimeError("HR approval returned an own response")
            return mutation.response

        return await self.unit_of_work.execute(operation)

    async def reject(
        self,
        request_id: UUID,
        payload: EmployeeProfileChangeRequestReject,
        *,
        request_context: RequestContext,
        granted_permissions: tuple[str, ...],
    ) -> EmployeeProfileChangeRequestHrDetailRead:
        tenant_id, membership_id, actor_user_id = _own_context(request_context)
        self._configure_database_command(
            intent=DatabaseCommandIntent.P4E_REJECT,
            target_id=request_id,
            request_context=request_context,
        )

        async def operation() -> EmployeeProfileChangeRequestHrDetailRead:
            mutation = await self.service.reject(
                tenant_id=tenant_id,
                membership_id=membership_id,
                actor_user_id=actor_user_id,
                granted_permissions=granted_permissions,
                request_id=request_id,
                payload=payload,
            )
            await self._record_event(
                mutation,
                request_context=request_context,
                event_type=AuditEventType.EMPLOYEE_PROFILE_CHANGE_REQUEST_REJECTED,
                action="reject_profile_change_request",
                reason_code="hr_rejected",
            )
            if not isinstance(mutation.response, EmployeeProfileChangeRequestHrDetailRead):
                raise RuntimeError("HR rejection returned an own response")
            return mutation.response

        return await self.unit_of_work.execute(operation)

    async def _record_event(
        self,
        mutation: EmployeeProfileChangeRequestMutation,
        *,
        request_context: RequestContext,
        event_type: AuditEventType,
        action: str,
        reason_code: str,
    ) -> None:
        if self._is_postgresql:
            # The checked P4E command function writes the value-free event in the same transaction.
            # Keeping the SQLite recorder preserves focused compatibility tests without a PG
            # duplicate.
            return
        actor_user_id = request_context.actor_id
        if actor_user_id is None:
            raise RuntimeError("Profile-change audit requires an authenticated actor")
        await self.audit_recorder.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=actor_user_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="employee_profile_change_request",
                resource_id=mutation.request_id,
                action=action,
                context=AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                changed_fields=mutation.changed_fields,
                metadata={
                    "request_id": mutation.request_id,
                    "employee_id": mutation.employee_id,
                    "before_request_status": mutation.before_status,
                    "after_request_status": mutation.after_status,
                    "reason_code": reason_code,
                },
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )

    def _configure_database_command(
        self,
        *,
        intent: DatabaseCommandIntent,
        target_id: UUID,
        request_context: RequestContext,
    ) -> None:
        if not self._is_postgresql:
            return
        tenant_id, membership_id, actor_user_id = _own_context(request_context)
        configure_database_command_context(
            self.service.session,
            DatabaseCommandContext(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                membership_id=membership_id,
                intent=intent,
                target_id=target_id,
                audit_event_id=uuid4(),
                correlation_request_id=request_context.request_id,
                trace_id=request_context.trace_id,
                session_id=request_context.session_id,
            ),
        )

    @property
    def _is_postgresql(self) -> bool:
        return self.service.session.get_bind().dialect.name == "postgresql"


def _own_context(request_context: RequestContext) -> tuple[UUID, UUID, UUID]:
    actor_user_id = request_context.actor_id
    if actor_user_id is None:
        raise RuntimeError("Profile-change commands require an authenticated actor")
    return (
        request_context.require_tenant().tenant_id,
        request_context.require_membership(),
        actor_user_id,
    )


__all__ = ["EmployeeProfileChangeRequestCommandHandler"]
