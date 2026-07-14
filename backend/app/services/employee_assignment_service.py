"""Effective-dated employee assignments and derived manager-team queries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.models.authorization import Permission, RolePermission, UserRole
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.employee_profile import (
    EmployeeEmploymentProfile,
    EmployeePersonalProfile,
)
from app.models.organization import (
    Branch,
    BranchStatus,
    LegalEntity,
    LegalEntityStatus,
)
from app.models.position import Position, PositionStatus
from app.models.user import User, UserStatus
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
from app.platform.db import SqlAlchemyUnitOfWork, configure_tenant_database_access
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.platform.request_context import RequestContext
from app.schemas.employee_assignment import (
    AssignmentBranchRead,
    AssignmentDepartmentRead,
    AssignmentEmployeeOptionRead,
    AssignmentEmployeeRead,
    AssignmentLegalEntityRead,
    AssignmentManagerOptionRead,
    AssignmentManagerRead,
    AssignmentPositionRead,
    EmployeeAssignmentChange,
    EmployeeAssignmentCreate,
    EmployeeAssignmentListPagination,
    EmployeeAssignmentOptionsRead,
    EmployeeAssignmentRead,
    ManagerTeamMemberProfileRead,
    TeamListPagination,
    TeamMemberRead,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.employee_field_projection import (
    WorkOrganizationSource,
    project_manager_assignment,
    project_manager_employee,
    project_manager_profile,
)
from app.services.employee_projection_contract import enforce_response_contract
from app.services.organization_access import (
    organization_scope_from_context,
    require_organization_permission,
    require_organization_tenant_access,
)

EMPLOYEE_ASSIGNMENT_READ_PERMISSION = "employee:read:tenant"
EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION = "employee:update:tenant"
EMPLOYEE_TEAM_READ_PERMISSION = "employee:read:team"


@dataclass(frozen=True, slots=True)
class EmployeeAssignmentProfileProjection:
    """Bounded Phase-3 assignment projection reused by Employee 360 reads."""

    current_assignment: EmployeeAssignmentRead | None
    history: list[EmployeeAssignmentRead]
    history_limit: int
    history_truncated: bool


class EmployeeAssignmentAccessDeniedError(ApplicationError):
    pass


class EmployeeAssignmentNotFoundError(ApplicationError):
    pass


class EmployeeAssignmentConflictError(ApplicationError):
    pass


class EmployeeAssignmentReferenceError(EmployeeAssignmentConflictError):
    pass


class EmployeeAssignmentService:
    """Own assignment history writes and derive direct-report scope from current rows."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = (SqlAlchemyAuditRecorder),
        today_factory: Callable[[], date] = date.today,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder_factory = audit_recorder_factory
        self._today_factory = today_factory

    async def list_assignments(
        self,
        *,
        request_context: RequestContext,
        pagination: EmployeeAssignmentListPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[EmployeeAssignmentRead]:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_ASSIGNMENT_READ_PERMISSION,
        )
        today = self._today_factory()
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(session, tenant_id, write=False)
                statement = _assignment_view_statement(tenant_id=tenant_id)
                if pagination.employee_id is not None:
                    statement = statement.where(
                        EmployeeAssignment.employee_id == pagination.employee_id
                    )
                if not pagination.include_history:
                    statement = statement.where(_effective_on(today))
                if pagination.cursor is not None:
                    statement = statement.where(_assignment_after_cursor(pagination.cursor))
                rows = list(
                    (
                        await session.execute(
                            statement.order_by(
                                Employee.employee_number.asc(),
                                EmployeeAssignment.effective_from.desc(),
                                EmployeeAssignment.id.asc(),
                            ).limit(pagination.limit + 1)
                        )
                    ).all()
                )
        items = [_assignment_read(row, today=today) for row in rows[: pagination.limit]]
        next_cursor = None
        if len(rows) > pagination.limit:
            last = items[-1]
            next_cursor = pagination.next_cursor(
                employee_number=last.employee.employee_number,
                effective_from=last.effective_from,
                assignment_id=last.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_assignment(
        self,
        *,
        request_context: RequestContext,
        assignment_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> EmployeeAssignmentRead:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_ASSIGNMENT_READ_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(session, tenant_id, write=False)
                row = (
                    await session.execute(
                        _assignment_view_statement(tenant_id=tenant_id).where(
                            EmployeeAssignment.id == assignment_id
                        )
                    )
                ).one_or_none()
        if row is None:
            raise EmployeeAssignmentNotFoundError()
        return _assignment_read(row, today=self._today_factory())

    async def assignment_options(
        self,
        *,
        request_context: RequestContext,
        search: str | None,
        limit: int,
        granted_permissions: tuple[str, ...],
    ) -> EmployeeAssignmentOptionsRead:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(session, tenant_id, write=False)
                open_assignment = aliased(EmployeeAssignment)
                employee_statement = (
                    select(Employee, open_assignment.id)
                    .outerjoin(
                        open_assignment,
                        and_(
                            open_assignment.tenant_id == Employee.tenant_id,
                            open_assignment.employee_id == Employee.id,
                            open_assignment.effective_to.is_(None),
                        ),
                    )
                    .where(
                        Employee.tenant_id == tenant_id,
                        Employee.archived_at.is_(None),
                        Employee.status.in_(
                            (
                                EmployeeStatus.ACTIVE.value,
                                EmployeeStatus.ON_LEAVE.value,
                            )
                        ),
                    )
                )
                if search is not None:
                    pattern = _contains_pattern(search)
                    employee_statement = employee_statement.where(
                        or_(
                            Employee.employee_number.ilike(pattern, escape="\\"),
                            Employee.first_name.ilike(pattern, escape="\\"),
                            Employee.last_name.ilike(pattern, escape="\\"),
                            (Employee.first_name + " " + Employee.last_name).ilike(
                                pattern, escape="\\"
                            ),
                            Employee.email.ilike(pattern, escape="\\"),
                        )
                    )
                employee_rows = list(
                    (
                        await session.execute(
                            employee_statement.order_by(
                                Employee.employee_number.asc(), Employee.id.asc()
                            ).limit(limit)
                        )
                    ).all()
                )

                manager_statement = select(User).where(
                    User.tenant_id == tenant_id,
                    User.status == UserStatus.ACTIVE.value,
                    _user_has_permission(EMPLOYEE_TEAM_READ_PERMISSION),
                )
                managers = list(
                    await session.scalars(
                        manager_statement.order_by(User.full_name.asc(), User.id.asc()).limit(limit)
                    )
                )

        return EmployeeAssignmentOptionsRead(
            employees=[
                AssignmentEmployeeOptionRead(
                    id=employee.id,
                    employee_number=employee.employee_number,
                    full_name=f"{employee.first_name} {employee.last_name}",
                    email=employee.email,
                    status=employee.status,
                    current_assignment_id=assignment_id,
                )
                for employee, assignment_id in employee_rows
            ],
            managers=[
                AssignmentManagerOptionRead(
                    id=manager.id,
                    full_name=manager.full_name,
                    email=manager.email,
                )
                for manager in managers
            ],
        )

    async def create_assignment(
        self,
        *,
        request_context: RequestContext,
        payload: EmployeeAssignmentCreate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> EmployeeAssignmentRead:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeAssignmentRead:
                await require_organization_tenant_access(session, tenant_id, write=True)
                (
                    employee,
                    legal_entity,
                    branch,
                    department,
                    position,
                    manager,
                ) = await _require_assignable_targets(
                    session,
                    tenant_id=tenant_id,
                    employee_id=payload.employee_id,
                    legal_entity_id=payload.legal_entity_id,
                    branch_id=payload.branch_id,
                    department_id=payload.department_id,
                    position_id=payload.position_id,
                    manager_user_id=payload.manager_id,
                )
                if await session.scalar(
                    select(EmployeeAssignment.id).where(
                        EmployeeAssignment.tenant_id == tenant_id,
                        EmployeeAssignment.employee_id == payload.employee_id,
                        EmployeeAssignment.effective_to.is_(None),
                    )
                ):
                    raise EmployeeAssignmentConflictError(
                        "Employee already has an open assignment; change that assignment instead"
                    )

                assignment = EmployeeAssignment(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    employee_id=payload.employee_id,
                    legal_entity_id=payload.legal_entity_id,
                    branch_id=payload.branch_id,
                    department_id=payload.department_id,
                    position_id=payload.position_id,
                    manager_user_id=payload.manager_id,
                    supersedes_assignment_id=None,
                    effective_from=payload.effective_from,
                    effective_to=None,
                    change_reason=payload.change_reason,
                    created_by_user_id=actor_id,
                )
                session.add(assignment)
                _update_legacy_projection_if_effective(
                    employee,
                    department=department,
                    position=position,
                    effective_from=assignment.effective_from,
                    today=self._today_factory(),
                )
                await session.flush()
                await session.refresh(assignment)
                result = _assignment_read_from_entities(
                    assignment=assignment,
                    employee=employee,
                    legal_entity=legal_entity,
                    branch=branch,
                    department=department,
                    position=position,
                    manager=manager,
                    today=self._today_factory(),
                )
                await self._record_change_events(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    assignment_id=assignment.id,
                    changed_fields=(
                        "legal_entity_id",
                        "branch_id",
                        "department_id",
                        "position_id",
                        "manager_id",
                        "effective_from",
                    ),
                    reporting_line_changed=payload.manager_id is not None,
                    action="create",
                )
                return result

            return await unit_of_work.execute(operation)

    async def change_assignment(
        self,
        *,
        request_context: RequestContext,
        assignment_id: UUID,
        payload: EmployeeAssignmentChange,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> EmployeeAssignmentRead:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION,
        )
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> EmployeeAssignmentRead:
                await require_organization_tenant_access(session, tenant_id, write=True)
                previous = await session.scalar(
                    select(EmployeeAssignment)
                    .where(
                        EmployeeAssignment.tenant_id == tenant_id,
                        EmployeeAssignment.id == assignment_id,
                    )
                    .with_for_update()
                )
                if previous is None:
                    raise EmployeeAssignmentNotFoundError()
                if previous.effective_to is not None:
                    raise EmployeeAssignmentConflictError(
                        "Historical assignments are immutable; change the open successor"
                    )
                if payload.effective_from < previous.effective_from:
                    raise EmployeeAssignmentConflictError(
                        "A successor cannot begin before the assignment it replaces"
                    )

                next_values = {
                    "legal_entity_id": previous.legal_entity_id,
                    "branch_id": previous.branch_id,
                    "department_id": previous.department_id,
                    "position_id": previous.position_id,
                    "manager_user_id": previous.manager_user_id,
                }
                public_to_model = {
                    "legal_entity_id": "legal_entity_id",
                    "branch_id": "branch_id",
                    "department_id": "department_id",
                    "position_id": "position_id",
                    "manager_id": "manager_user_id",
                }
                for public_name, model_name in public_to_model.items():
                    if public_name in payload.model_fields_set:
                        next_values[model_name] = getattr(payload, public_name)

                changed_fields = tuple(
                    public_name
                    for public_name, model_name in public_to_model.items()
                    if next_values[model_name] != getattr(previous, model_name)
                )
                if not changed_fields:
                    raise EmployeeAssignmentConflictError(
                        "The assignment change must alter organization or manager scope"
                    )

                (
                    employee,
                    legal_entity,
                    branch,
                    department,
                    position,
                    manager,
                ) = await _require_assignable_targets(
                    session,
                    tenant_id=tenant_id,
                    employee_id=previous.employee_id,
                    legal_entity_id=next_values["legal_entity_id"],
                    branch_id=next_values["branch_id"],
                    department_id=next_values["department_id"],
                    position_id=next_values["position_id"],
                    manager_user_id=next_values["manager_user_id"],
                )

                now = datetime.now(UTC)
                previous.effective_to = payload.effective_from
                previous.updated_at = now
                await session.flush()
                successor = EmployeeAssignment(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    employee_id=previous.employee_id,
                    legal_entity_id=next_values["legal_entity_id"],
                    branch_id=next_values["branch_id"],
                    department_id=next_values["department_id"],
                    position_id=next_values["position_id"],
                    manager_user_id=next_values["manager_user_id"],
                    supersedes_assignment_id=previous.id,
                    effective_from=payload.effective_from,
                    effective_to=None,
                    change_reason=payload.change_reason,
                    created_by_user_id=actor_id,
                )
                session.add(successor)
                _update_legacy_projection_if_effective(
                    employee,
                    department=department,
                    position=position,
                    effective_from=successor.effective_from,
                    today=self._today_factory(),
                )
                await session.flush()
                await session.refresh(successor)
                result = _assignment_read_from_entities(
                    assignment=successor,
                    employee=employee,
                    legal_entity=legal_entity,
                    branch=branch,
                    department=department,
                    position=position,
                    manager=manager,
                    today=self._today_factory(),
                )
                await self._record_change_events(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    assignment_id=successor.id,
                    changed_fields=tuple(sorted((*changed_fields, "effective_from"))),
                    reporting_line_changed="manager_id" in changed_fields,
                    action="change",
                )
                return result

            return await unit_of_work.execute(operation)

    async def my_team(
        self,
        *,
        request_context: RequestContext,
        pagination: TeamListPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[TeamMemberRead]:
        tenant_id, actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_TEAM_READ_PERMISSION,
        )
        today = self._today_factory()
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(session, tenant_id, write=False)
                statement = _manager_team_view_statement(tenant_id=tenant_id).where(
                    EmployeeAssignment.manager_user_id == actor_id,
                    _effective_on(today),
                    Employee.archived_at.is_(None),
                    Employee.status.in_(
                        (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
                    ),
                )
                if pagination.cursor is not None:
                    statement = statement.where(
                        or_(
                            Employee.employee_number > pagination.cursor.employee_number,
                            and_(
                                Employee.employee_number == pagination.cursor.employee_number,
                                Employee.id > pagination.cursor.id,
                            ),
                        )
                    )
                rows = list(
                    (
                        await session.execute(
                            statement.order_by(
                                Employee.employee_number.asc(), Employee.id.asc()
                            ).limit(pagination.limit + 1)
                        )
                    ).all()
                )
        items = []
        for row in rows[: pagination.limit]:
            employee, organization, _employment = _manager_team_projection_values(row)
            item = TeamMemberRead(
                employee=employee,
                assignment=project_manager_assignment(organization),
            )
            enforce_response_contract(item)
            items.append(item)
        next_cursor = None
        if len(rows) > pagination.limit:
            last = items[-1].employee
            from app.schemas.employee_assignment import TeamListCursor

            next_cursor = TeamListCursor(
                employee_number=last.employee_number,
                id=last.id,
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def manager_team_member_profile(
        self,
        *,
        request_context: RequestContext,
        employee_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> ManagerTeamMemberProfileRead:
        """Read one current direct report; indirect and historical scope is intentionally absent."""

        tenant_id, actor_id = organization_scope_from_context(request_context)
        _require_assignment_permission(
            granted_permissions,
            EMPLOYEE_TEAM_READ_PERMISSION,
        )
        today = self._today_factory()
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(session, tenant_id, write=False)
                row = (
                    await session.execute(
                        _manager_team_view_statement(tenant_id=tenant_id)
                        .where(
                            Employee.id == employee_id,
                            EmployeeAssignment.manager_user_id == actor_id,
                            _effective_on(today),
                            Employee.archived_at.is_(None),
                            Employee.status.in_(
                                (
                                    EmployeeStatus.ACTIVE.value,
                                    EmployeeStatus.ON_LEAVE.value,
                                )
                            ),
                        )
                        .limit(1)
                    )
                ).one_or_none()
        if row is None:
            raise EmployeeAssignmentNotFoundError
        employee, organization, employment = _manager_team_projection_values(row)
        employment_start_date, contract_type, work_type = employment
        return project_manager_profile(
            core=employee,
            employment_start_date=employment_start_date,
            contract_type=contract_type,
            work_type=work_type,
            organization=organization,
        )

    async def _record_change_events(
        self,
        session: AsyncSession,
        *,
        request_context: RequestContext,
        audit_context: AuditContext | None,
        actor_id: UUID,
        assignment_id: UUID,
        changed_fields: tuple[str, ...],
        reporting_line_changed: bool,
        action: str,
    ) -> None:
        recorder = self._audit_recorder_factory(session)
        common = {
            "scope_type": AuditScopeType.TENANT,
            "tenant_id": request_context.require_tenant().tenant_id,
            "actor_type": AuditActorType.USER,
            "actor_user_id": actor_id,
            "category": AuditCategory.HR_OPERATIONS,
            "resource_type": "employee_assignment",
            "resource_id": assignment_id,
            "context": audit_context or AuditContext.from_request_context(request_context),
            "session_id": request_context.session_id,
            "data_classification": AuditDataClassification.HR_METADATA,
            "visibility_class": AuditVisibilityClass.HR_OPERATIONS,
        }
        await recorder.record(
            AuditEventDraft(
                **common,
                event_type=AuditEventType.EMPLOYEE_ASSIGNMENT_CHANGED,
                action=action,
                changed_fields=changed_fields,
            )
        )
        if reporting_line_changed:
            await recorder.record(
                AuditEventDraft(
                    **common,
                    event_type=AuditEventType.REPORTING_LINE_CHANGED,
                    action=action,
                    changed_fields=("manager_id",),
                )
            )


def _require_assignment_permission(
    granted_permissions: tuple[str, ...],
    permission: str,
) -> None:
    try:
        require_organization_permission(granted_permissions, permission)
    except ApplicationError as exc:
        raise EmployeeAssignmentAccessDeniedError() from exc


async def _require_assignable_targets(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    employee_id: UUID,
    legal_entity_id: UUID,
    branch_id: UUID,
    department_id: UUID,
    position_id: UUID,
    manager_user_id: UUID | None,
) -> tuple[Employee, LegalEntity, Branch, Department, Position, User | None]:
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.id == employee_id,
        )
    )
    if employee is None:
        raise EmployeeAssignmentReferenceError("Employee was not found")
    if employee.archived_at is not None or employee.status == EmployeeStatus.TERMINATED.value:
        raise EmployeeAssignmentReferenceError(
            "Archived or terminated employees cannot receive a new assignment"
        )

    legal_entity = await session.scalar(
        select(LegalEntity).where(
            LegalEntity.tenant_id == tenant_id,
            LegalEntity.id == legal_entity_id,
        )
    )
    if legal_entity is None or legal_entity.status != LegalEntityStatus.ACTIVE.value:
        raise EmployeeAssignmentReferenceError("Assignments require an active legal entity")

    branch = await session.scalar(
        select(Branch).where(
            Branch.tenant_id == tenant_id,
            Branch.id == branch_id,
        )
    )
    if (
        branch is None
        or branch.status != BranchStatus.ACTIVE.value
        or branch.archived_at is not None
        or branch.legal_entity_id != legal_entity_id
    ):
        raise EmployeeAssignmentReferenceError(
            "Assignments require an active branch under the selected legal entity"
        )

    department = await session.scalar(
        select(Department).where(
            Department.tenant_id == tenant_id,
            Department.id == department_id,
        )
    )
    if (
        department is None
        or department.status != DepartmentStatus.ACTIVE.value
        or department.archived_at is not None
    ):
        raise EmployeeAssignmentReferenceError("Assignments require an active department")

    position = await session.scalar(
        select(Position).where(
            Position.tenant_id == tenant_id,
            Position.id == position_id,
        )
    )
    if (
        position is None
        or position.status != PositionStatus.ACTIVE.value
        or position.archived_at is not None
    ):
        raise EmployeeAssignmentReferenceError("Assignments require an active position")

    manager = None
    if manager_user_id is not None:
        manager = await session.scalar(
            select(User).where(
                User.tenant_id == tenant_id,
                User.id == manager_user_id,
                User.status == UserStatus.ACTIVE.value,
                _user_has_permission(EMPLOYEE_TEAM_READ_PERMISSION),
            )
        )
        if manager is None:
            raise EmployeeAssignmentReferenceError(
                "The reporting manager must be an active user with team access"
            )
        if (
            employee.email is not None
            and employee.email.strip().casefold() == manager.email.strip().casefold()
        ):
            raise EmployeeAssignmentReferenceError(
                "An employee cannot be their own reporting manager"
            )
    return employee, legal_entity, branch, department, position, manager


async def employee_assignment_profile_projection(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    employee_id: UUID,
    effective_on: date,
    history_limit: int,
) -> EmployeeAssignmentProfileProjection:
    """Read current organization and bounded history from the Phase-3 source of truth.

    Authorization stays at the Employee 360 API edge. This shared query deliberately does not
    apply the organization feature gate because profile reads require employee-read permission
    and must remain usable without granting organization-management access.
    """

    if not 1 <= history_limit <= 100:
        raise ValueError("Assignment profile history limit must be between 1 and 100")

    current_row = (
        await session.execute(
            _assignment_view_statement(tenant_id=tenant_id).where(
                EmployeeAssignment.employee_id == employee_id,
                _effective_on(effective_on),
            )
        )
    ).one_or_none()
    history_rows = list(
        (
            await session.execute(
                _assignment_view_statement(tenant_id=tenant_id)
                .where(
                    EmployeeAssignment.employee_id == employee_id,
                    EmployeeAssignment.effective_from <= effective_on,
                )
                .order_by(
                    EmployeeAssignment.effective_from.desc(),
                    EmployeeAssignment.id.asc(),
                )
                .limit(history_limit + 1)
            )
        ).all()
    )
    return EmployeeAssignmentProfileProjection(
        current_assignment=(
            _assignment_read(current_row, today=effective_on) if current_row is not None else None
        ),
        history=[_assignment_read(row, today=effective_on) for row in history_rows[:history_limit]],
        history_limit=history_limit,
        history_truncated=len(history_rows) > history_limit,
    )


def _user_has_permission(permission_code: str):
    return exists(
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            UserRole.tenant_id == User.tenant_id,
            UserRole.user_id == User.id,
            UserRole.active.is_(True),
            Permission.code == permission_code,
        )
    )


def _manager_team_view_statement(*, tenant_id: UUID):
    """Select only fields classified work-safe for a current direct-team projection."""

    manager = aliased(User, name="team_profile_manager")
    return (
        select(
            Employee.id,
            Employee.employee_number,
            Employee.first_name,
            Employee.last_name,
            EmployeePersonalProfile.preferred_name,
            Employee.email,
            Employee.status,
            Employee.employment_start_date,
            EmployeeEmploymentProfile.contract_type,
            EmployeeEmploymentProfile.work_type,
            LegalEntity.code,
            LegalEntity.name,
            Branch.code,
            Branch.name,
            Department.code,
            Department.name,
            Position.code,
            Position.title,
            manager.full_name,
            EmployeeAssignment.effective_from,
        )
        .select_from(EmployeeAssignment)
        .join(
            Employee,
            and_(
                Employee.tenant_id == EmployeeAssignment.tenant_id,
                Employee.id == EmployeeAssignment.employee_id,
            ),
        )
        .outerjoin(
            EmployeePersonalProfile,
            and_(
                EmployeePersonalProfile.tenant_id == Employee.tenant_id,
                EmployeePersonalProfile.employee_id == Employee.id,
            ),
        )
        .outerjoin(
            EmployeeEmploymentProfile,
            and_(
                EmployeeEmploymentProfile.tenant_id == Employee.tenant_id,
                EmployeeEmploymentProfile.employee_id == Employee.id,
            ),
        )
        .join(
            LegalEntity,
            and_(
                LegalEntity.tenant_id == EmployeeAssignment.tenant_id,
                LegalEntity.id == EmployeeAssignment.legal_entity_id,
            ),
        )
        .join(
            Branch,
            and_(
                Branch.tenant_id == EmployeeAssignment.tenant_id,
                Branch.id == EmployeeAssignment.branch_id,
            ),
        )
        .join(
            Department,
            and_(
                Department.tenant_id == EmployeeAssignment.tenant_id,
                Department.id == EmployeeAssignment.department_id,
            ),
        )
        .join(
            Position,
            and_(
                Position.tenant_id == EmployeeAssignment.tenant_id,
                Position.id == EmployeeAssignment.position_id,
            ),
        )
        .join(
            manager,
            and_(
                manager.tenant_id == EmployeeAssignment.tenant_id,
                manager.id == EmployeeAssignment.manager_user_id,
            ),
        )
        .where(EmployeeAssignment.tenant_id == tenant_id)
    )


def _manager_team_projection_values(row):
    (
        employee_id,
        employee_number,
        first_name,
        last_name,
        preferred_name,
        email,
        status,
        employment_start_date,
        contract_type,
        work_type,
        legal_entity_code,
        legal_entity_name,
        branch_code,
        branch_name,
        department_code,
        department_name,
        position_code,
        position_title,
        manager_full_name,
        effective_from,
    ) = row
    employee = project_manager_employee(
        employee_id=employee_id,
        employee_number=employee_number,
        first_name=first_name,
        last_name=last_name,
        preferred_name=preferred_name,
        email=email,
        status=status,
    )
    organization = WorkOrganizationSource(
        legal_entity_code=legal_entity_code,
        legal_entity_name=legal_entity_name,
        branch_code=branch_code,
        branch_name=branch_name,
        department_code=department_code,
        department_name=department_name,
        position_code=position_code,
        position_title=position_title,
        manager_full_name=manager_full_name,
        effective_from=effective_from,
    )
    return employee, organization, (employment_start_date, contract_type, work_type)


def _assignment_view_statement(*, tenant_id: UUID):
    manager = aliased(User, name="assignment_manager")
    return (
        select(
            EmployeeAssignment,
            Employee,
            LegalEntity,
            Branch,
            Department,
            Position,
            manager,
        )
        .join(
            Employee,
            and_(
                Employee.tenant_id == EmployeeAssignment.tenant_id,
                Employee.id == EmployeeAssignment.employee_id,
            ),
        )
        .join(
            LegalEntity,
            and_(
                LegalEntity.tenant_id == EmployeeAssignment.tenant_id,
                LegalEntity.id == EmployeeAssignment.legal_entity_id,
            ),
        )
        .join(
            Branch,
            and_(
                Branch.tenant_id == EmployeeAssignment.tenant_id,
                Branch.id == EmployeeAssignment.branch_id,
            ),
        )
        .join(
            Department,
            and_(
                Department.tenant_id == EmployeeAssignment.tenant_id,
                Department.id == EmployeeAssignment.department_id,
            ),
        )
        .join(
            Position,
            and_(
                Position.tenant_id == EmployeeAssignment.tenant_id,
                Position.id == EmployeeAssignment.position_id,
            ),
        )
        .outerjoin(
            manager,
            and_(
                manager.tenant_id == EmployeeAssignment.tenant_id,
                manager.id == EmployeeAssignment.manager_user_id,
            ),
        )
        .where(EmployeeAssignment.tenant_id == tenant_id)
    )


def _effective_on(day: date):
    return and_(
        EmployeeAssignment.effective_from <= day,
        or_(
            EmployeeAssignment.effective_to.is_(None),
            EmployeeAssignment.effective_to > day,
        ),
    )


def _assignment_after_cursor(cursor):
    return or_(
        Employee.employee_number > cursor.employee_number,
        and_(
            Employee.employee_number == cursor.employee_number,
            EmployeeAssignment.effective_from < cursor.effective_from,
        ),
        and_(
            Employee.employee_number == cursor.employee_number,
            EmployeeAssignment.effective_from == cursor.effective_from,
            EmployeeAssignment.id > cursor.id,
        ),
    )


def _assignment_read(row, *, today: date) -> EmployeeAssignmentRead:
    assignment, employee, legal_entity, branch, department, position, manager = row
    return _assignment_read_from_entities(
        assignment=assignment,
        employee=employee,
        legal_entity=legal_entity,
        branch=branch,
        department=department,
        position=position,
        manager=manager,
        today=today,
    )


def _assignment_read_from_entities(
    *,
    assignment: EmployeeAssignment,
    employee: Employee,
    legal_entity: LegalEntity,
    branch: Branch,
    department: Department,
    position: Position,
    manager: User | None,
    today: date,
) -> EmployeeAssignmentRead:
    return EmployeeAssignmentRead(
        id=assignment.id,
        employee=AssignmentEmployeeRead(
            id=employee.id,
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email,
            status=employee.status,
        ),
        legal_entity=AssignmentLegalEntityRead(
            id=legal_entity.id,
            code=legal_entity.code,
            name=legal_entity.name,
            status=legal_entity.status,
        ),
        branch=AssignmentBranchRead(
            id=branch.id,
            code=branch.code,
            name=branch.name,
            status=branch.status,
        ),
        department=AssignmentDepartmentRead(
            id=department.id,
            code=department.code,
            name=department.name,
            status=department.status,
        ),
        position=AssignmentPositionRead(
            id=position.id,
            code=position.code,
            title=position.title,
            status=position.status,
        ),
        manager=(
            AssignmentManagerRead(
                id=manager.id,
                full_name=manager.full_name,
                email=manager.email,
                status=manager.status,
            )
            if manager is not None
            else None
        ),
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        supersedes_assignment_id=assignment.supersedes_assignment_id,
        change_reason=assignment.change_reason,
        is_current=(
            assignment.effective_from <= today
            and (assignment.effective_to is None or assignment.effective_to > today)
        ),
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


def _update_legacy_projection_if_effective(
    employee: Employee,
    *,
    department: Department,
    position: Position,
    effective_from: date,
    today: date,
) -> None:
    if effective_from <= today:
        employee.department = department.name
        employee.position = position.title


def _contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


__all__ = [
    "EMPLOYEE_ASSIGNMENT_READ_PERMISSION",
    "EMPLOYEE_ASSIGNMENT_UPDATE_PERMISSION",
    "EMPLOYEE_TEAM_READ_PERMISSION",
    "EmployeeAssignmentAccessDeniedError",
    "EmployeeAssignmentConflictError",
    "EmployeeAssignmentNotFoundError",
    "EmployeeAssignmentReferenceError",
    "EmployeeAssignmentProfileProjection",
    "EmployeeAssignmentService",
    "employee_assignment_profile_projection",
]
