"""Query-efficient lazy reporting hierarchy for the organization workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_assignment import EmployeeAssignment
from app.models.organization import Branch, BranchStatus, LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
from app.models.user import User
from app.platform.db import configure_tenant_database_access
from app.platform.pagination import CursorPage
from app.platform.request_context import RequestContext
from app.schemas.employee_assignment import (
    AssignmentBranchRead,
    AssignmentDepartmentRead,
    AssignmentLegalEntityRead,
    AssignmentPositionRead,
)
from app.schemas.org_chart import OrgChartNodeRead, OrgChartPagination
from app.services.organization_access import (
    ORGANIZATION_READ_PERMISSION,
    organization_scope_from_context,
    require_organization_permission,
    require_organization_tenant_access,
)


@dataclass(frozen=True, slots=True)
class _SortedNode:
    node: OrgChartNodeRead

    @property
    def key(self) -> tuple[int, str]:
        return (_node_type_rank(self.node.node_type), self.node.id.hex)


def _node_type_rank(node_type: Literal["employee", "manager"]) -> int:
    # Synthetic manager roots precede unassigned employee roots. UUID is the portable stable
    # key: unlike display-name ordering it cannot diverge across Python and database collations.
    return 0 if node_type == "manager" else 1


class OrganizationChartService:
    """Return one capped reporting level with a fixed number of SQL statements.

    Phase 3 does not yet have the explicit Employee/User link planned for Phase 4. Until that
    expand-side relation exists, a tenant-scoped normalized work email is the compatibility link
    that lets an employee node become an expandable reporting manager. A referenced manager User
    without an Employee row is represented as a synthetic root so existing demo and migrated
    assignments never produce an empty chart.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        today_factory=date.today,
    ) -> None:
        self._session_factory = session_factory
        self._today_factory = today_factory

    async def list_level(
        self,
        *,
        request_context: RequestContext,
        pagination: OrgChartPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[OrgChartNodeRead]:
        tenant_id, _actor_id = organization_scope_from_context(request_context)
        require_organization_permission(
            granted_permissions,
            ORGANIZATION_READ_PERMISSION,
        )
        today = self._today_factory()
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await require_organization_tenant_access(session, tenant_id, write=False)
                employee_rows = list(
                    (
                        await session.execute(
                            _employee_node_statement(
                                tenant_id=tenant_id,
                                today=today,
                                pagination=pagination,
                            ).limit(pagination.limit + 1)
                        )
                    ).all()
                )
                manager_rows = []
                if pagination.parent_id is None:
                    manager_rows = list(
                        (
                            await session.execute(
                                _manager_root_statement(
                                    tenant_id=tenant_id,
                                    today=today,
                                    pagination=pagination,
                                ).limit(pagination.limit + 1)
                            )
                        ).all()
                    )

        candidates = [_employee_node(row) for row in employee_rows]
        candidates.extend(_manager_node(row) for row in manager_rows)
        candidates.sort(key=lambda item: item.key)
        visible = candidates[: pagination.limit]
        next_cursor = None
        if len(candidates) > pagination.limit:
            last = visible[-1]
            next_cursor = pagination.next_cursor(
                node_type=last.node.node_type,
                node_id=last.node.id,
            )
        return CursorPage(
            items=[item.node for item in visible],
            next_cursor=next_cursor,
        )


def _visible_employee_predicates(
    assignment,
    employee,
    *,
    tenant_id: UUID,
    today: date,
):
    return (
        assignment.tenant_id == tenant_id,
        assignment.effective_from <= today,
        or_(assignment.effective_to.is_(None), assignment.effective_to > today),
        employee.tenant_id == assignment.tenant_id,
        employee.id == assignment.employee_id,
        employee.archived_at.is_(None),
        employee.status.in_(
            (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
        ),
    )


def _employee_node_statement(
    *,
    tenant_id: UUID,
    today: date,
    pagination: OrgChartPagination,
):
    linked_user = aliased(User, name="org_chart_linked_user")
    child_assignment = aliased(EmployeeAssignment, name="org_chart_child_assignment")
    child_employee = aliased(Employee, name="org_chart_child_employee")
    node_id = Employee.id
    has_children = exists(
        select(child_assignment.id)
        .join(
            child_employee,
            and_(
                child_employee.tenant_id == child_assignment.tenant_id,
                child_employee.id == child_assignment.employee_id,
            ),
        )
        .where(
            child_assignment.tenant_id == tenant_id,
            child_assignment.manager_user_id == linked_user.id,
            child_assignment.effective_from <= today,
            or_(
                child_assignment.effective_to.is_(None),
                child_assignment.effective_to > today,
            ),
            child_employee.archived_at.is_(None),
            child_employee.status.in_(
                (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
            ),
        )
    )
    statement = (
        select(
            EmployeeAssignment,
            Employee,
            LegalEntity,
            Branch,
            Department,
            Position,
            linked_user,
            has_children.label("has_children"),
            node_id.label("node_id"),
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
            linked_user,
            and_(
                linked_user.tenant_id == EmployeeAssignment.tenant_id,
                Employee.email.is_not(None),
                linked_user.email_normalized == func.lower(func.trim(Employee.email)),
            ),
        )
        .where(
            *_visible_employee_predicates(
                EmployeeAssignment,
                Employee,
                tenant_id=tenant_id,
                today=today,
            )
        )
    )
    if pagination.parent_id is None:
        statement = statement.where(EmployeeAssignment.manager_user_id.is_(None))
    else:
        statement = statement.where(
            EmployeeAssignment.manager_user_id == pagination.parent_id
        )
    if pagination.cursor is not None:
        statement = statement.where(
            _after_cursor(
                node_type="employee",
                node_id=node_id,
                pagination=pagination,
            )
        )
    return statement.order_by(node_id.asc())


def _manager_root_statement(
    *,
    tenant_id: UUID,
    today: date,
    pagination: OrgChartPagination,
):
    child_assignment = aliased(EmployeeAssignment, name="org_chart_root_child_assignment")
    child_employee = aliased(Employee, name="org_chart_root_child_employee")
    own_assignment = aliased(EmployeeAssignment, name="org_chart_manager_own_assignment")
    own_employee = aliased(Employee, name="org_chart_manager_own_employee")
    has_visible_children = exists(
        select(child_assignment.id)
        .join(
            child_employee,
            and_(
                child_employee.tenant_id == child_assignment.tenant_id,
                child_employee.id == child_assignment.employee_id,
            ),
        )
        .where(
            child_assignment.tenant_id == tenant_id,
            child_assignment.manager_user_id == User.id,
            child_assignment.effective_from <= today,
            or_(
                child_assignment.effective_to.is_(None),
                child_assignment.effective_to > today,
            ),
            child_employee.archived_at.is_(None),
            child_employee.status.in_(
                (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
            ),
        )
    )
    appears_as_employee = exists(
        select(own_assignment.id)
        .join(
            own_employee,
            and_(
                own_employee.tenant_id == own_assignment.tenant_id,
                own_employee.id == own_assignment.employee_id,
            ),
        )
        .where(
            own_assignment.tenant_id == tenant_id,
            own_assignment.effective_from <= today,
            or_(own_assignment.effective_to.is_(None), own_assignment.effective_to > today),
            own_employee.archived_at.is_(None),
            own_employee.status.in_(
                (EmployeeStatus.ACTIVE.value, EmployeeStatus.ON_LEAVE.value)
            ),
            own_employee.email.is_not(None),
            func.lower(func.trim(own_employee.email)) == User.email_normalized,
        )
    )
    statement = select(User).where(
        User.tenant_id == tenant_id,
        has_visible_children,
        ~appears_as_employee,
    )
    if pagination.cursor is not None:
        statement = statement.where(
            _after_cursor(
                node_type="manager",
                node_id=User.id,
                pagination=pagination,
            )
        )
    return statement.order_by(User.id.asc())


def _after_cursor(
    *,
    node_type: Literal["employee", "manager"],
    node_id,
    pagination: OrgChartPagination,
):
    cursor = pagination.cursor
    if cursor is None:
        raise ValueError("Cursor predicate requires a cursor")
    node_rank = _node_type_rank(node_type)
    cursor_rank = _node_type_rank(cursor.node_type)
    if node_rank != cursor_rank:
        return literal(node_rank > cursor_rank)
    return node_id > cursor.id


def _employee_node(row) -> _SortedNode:
    (
        assignment,
        employee,
        legal_entity,
        branch,
        department,
        position,
        linked_user,
        has_children,
        node_id,
    ) = row
    return _SortedNode(
        node=OrgChartNodeRead(
            id=node_id,
            node_type="employee",
            employee_id=employee.id,
            user_id=linked_user.id if linked_user is not None else None,
            parent_user_id=assignment.manager_user_id,
            assignment_id=assignment.id,
            full_name=f"{employee.first_name} {employee.last_name}".strip(),
            email=employee.email,
            employee_number=employee.employee_number,
            employee_status=employee.status,
            user_status=linked_user.status if linked_user is not None else None,
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
            has_children=bool(has_children),
            has_archived_reference=(
                legal_entity.status != LegalEntityStatus.ACTIVE.value
                or branch.status != BranchStatus.ACTIVE.value
                or department.status != DepartmentStatus.ACTIVE.value
                or position.status != PositionStatus.ACTIVE.value
            ),
        ),
    )


def _manager_node(row) -> _SortedNode:
    (manager,) = row
    return _SortedNode(
        node=OrgChartNodeRead(
            id=manager.id,
            node_type="manager",
            employee_id=None,
            user_id=manager.id,
            parent_user_id=None,
            assignment_id=None,
            full_name=manager.full_name,
            email=manager.email,
            employee_number=None,
            employee_status=None,
            user_status=manager.status,
            legal_entity=None,
            branch=None,
            department=None,
            position=None,
            has_children=True,
            has_archived_reference=False,
        ),
    )


__all__ = ["OrganizationChartService"]
