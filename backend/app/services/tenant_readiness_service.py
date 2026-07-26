"""Read-only bounded tenant setup-readiness projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.authorization import Role
from app.models.department import Department, DepartmentStatus
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_document import DocumentType
from app.models.identity import MembershipRole, MembershipStatus, TenantMembership
from app.models.leave import HolidayCalendar, LeavePolicy, LeaveType
from app.models.organization import LegalEntity, LegalEntityStatus
from app.models.position import Position, PositionStatus
from app.models.privacy import PrivacyNotice, PrivacyNoticeKind, PrivacyNoticeStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.modules.documents import DocumentRuntime
from app.platform.authorization import RoleScopeType
from app.platform.request_context import RequestContext
from app.schemas.tenant_readiness import (
    TenantReadinessItemKey,
    TenantReadinessItemRead,
    TenantReadinessItemState,
    TenantReadinessOverallState,
    TenantReadinessRead,
)
from app.services.tenant_feature_service import TenantFeatureService


@dataclass(frozen=True, slots=True)
class _ReadinessFacts:
    active_default_legal_entity_count: int
    has_active_department: bool
    has_active_position: bool
    active_tenant_administrator_count: int
    active_employee_count: int
    has_active_leave_type: bool
    active_default_holiday_calendar_count: int
    has_active_leave_type_without_effective_policy: bool
    active_document_type_count: int
    current_published_privacy_notice_count: int


class TenantReadinessService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        feature_service: TenantFeatureService,
        settings: Settings,
        document_runtime: DocumentRuntime,
    ) -> None:
        self.session = session
        self.feature_service = feature_service
        self.settings = settings
        self.document_runtime = document_runtime

    async def get(self, *, request_context: RequestContext) -> TenantReadinessRead:
        tenant_id = request_context.require_tenant().tenant_id
        if request_context.actor_id is None:
            raise RuntimeError("Tenant readiness requires an authenticated actor")
        request_context.require_membership()

        evaluated_at = datetime.now(UTC)
        effective_on = evaluated_at.date()
        features = await self.feature_service.get_tenant_features(
            tenant_id,
            enforce_tenant_lifecycle=True,
        )
        enabled = {feature.key: feature.enabled for feature in features}
        if set(enabled) != set(FeatureFlagKey):
            raise RuntimeError("Tenant feature catalog is incomplete")

        facts = await self._facts(tenant_id=tenant_id, effective_on=effective_on)
        items = self._items(
            evaluated_at=evaluated_at,
            enabled=enabled,
            facts=facts,
        )
        overall_state = (
            TenantReadinessOverallState.READY
            if all(
                item.state
                in {
                    TenantReadinessItemState.READY,
                    TenantReadinessItemState.NOT_APPLICABLE,
                }
                for item in items
            )
            else TenantReadinessOverallState.ACTION_REQUIRED
        )
        return TenantReadinessRead(
            overall_state=overall_state,
            evaluated_at=evaluated_at,
            items=items,
        )

    async def _facts(self, *, tenant_id: UUID, effective_on: date) -> _ReadinessFacts:
        active_default_legal_entity_count = (
            select(func.count())
            .select_from(LegalEntity)
            .where(
                LegalEntity.tenant_id == tenant_id,
                LegalEntity.status == LegalEntityStatus.ACTIVE.value,
                LegalEntity.is_default.is_(True),
            )
            .scalar_subquery()
        )
        active_tenant_administrator_count = (
            select(func.count(func.distinct(TenantMembership.id)))
            .select_from(TenantMembership)
            .join(
                MembershipRole,
                and_(
                    MembershipRole.tenant_id == TenantMembership.tenant_id,
                    MembershipRole.membership_id == TenantMembership.id,
                ),
            )
            .join(
                Role,
                and_(
                    Role.id == MembershipRole.role_id,
                    Role.scope_type == MembershipRole.role_scope_type,
                ),
            )
            .where(
                TenantMembership.tenant_id == tenant_id,
                MembershipRole.tenant_id == tenant_id,
                TenantMembership.status == MembershipStatus.ACTIVE.value,
                MembershipRole.active.is_(True),
                MembershipRole.role_scope_type == RoleScopeType.TENANT.value,
                Role.code == "tenant_admin",
            )
            .scalar_subquery()
        )
        active_employee_count = (
            select(func.count())
            .select_from(Employee)
            .where(
                Employee.tenant_id == tenant_id,
                Employee.status == EmployeeStatus.ACTIVE.value,
                Employee.archived_at.is_(None),
            )
            .scalar_subquery()
        )
        active_default_holiday_calendar_count = (
            select(func.count())
            .select_from(HolidayCalendar)
            .where(
                HolidayCalendar.tenant_id == tenant_id,
                HolidayCalendar.is_active.is_(True),
                HolidayCalendar.is_default.is_(True),
            )
            .scalar_subquery()
        )
        active_document_type_count = (
            select(func.count())
            .select_from(DocumentType)
            .where(
                DocumentType.tenant_id == tenant_id,
                DocumentType.archived_at.is_(None),
            )
            .scalar_subquery()
        )
        current_published_privacy_notice_count = (
            select(func.count())
            .select_from(PrivacyNotice)
            .where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
                PrivacyNotice.status == PrivacyNoticeStatus.PUBLISHED.value,
            )
            .scalar_subquery()
        )
        effective_policy_for_active_type = exists(
            select(LeavePolicy.id)
            .where(
                LeavePolicy.tenant_id == tenant_id,
                LeavePolicy.leave_type_id == LeaveType.id,
                LeavePolicy.effective_from <= effective_on,
            )
            .correlate(LeaveType)
        )

        row = (
            (
                await self.session.execute(
                    select(
                        active_default_legal_entity_count.label(
                            "active_default_legal_entity_count"
                        ),
                        exists(
                            select(Department.id).where(
                                Department.tenant_id == tenant_id,
                                Department.status == DepartmentStatus.ACTIVE.value,
                            )
                        ).label("has_active_department"),
                        exists(
                            select(Position.id).where(
                                Position.tenant_id == tenant_id,
                                Position.status == PositionStatus.ACTIVE.value,
                            )
                        ).label("has_active_position"),
                        active_tenant_administrator_count.label(
                            "active_tenant_administrator_count"
                        ),
                        active_employee_count.label("active_employee_count"),
                        exists(
                            select(LeaveType.id).where(
                                LeaveType.tenant_id == tenant_id,
                                LeaveType.is_active.is_(True),
                            )
                        ).label("has_active_leave_type"),
                        active_default_holiday_calendar_count.label(
                            "active_default_holiday_calendar_count"
                        ),
                        exists(
                            select(LeaveType.id).where(
                                LeaveType.tenant_id == tenant_id,
                                LeaveType.is_active.is_(True),
                                ~effective_policy_for_active_type,
                            )
                        ).label("has_active_leave_type_without_effective_policy"),
                        active_document_type_count.label("active_document_type_count"),
                        current_published_privacy_notice_count.label(
                            "current_published_privacy_notice_count"
                        ),
                    )
                )
            )
            .mappings()
            .one()
        )
        return _ReadinessFacts(
            active_default_legal_entity_count=int(row["active_default_legal_entity_count"] or 0),
            has_active_department=bool(row["has_active_department"]),
            has_active_position=bool(row["has_active_position"]),
            active_tenant_administrator_count=int(row["active_tenant_administrator_count"] or 0),
            active_employee_count=int(row["active_employee_count"] or 0),
            has_active_leave_type=bool(row["has_active_leave_type"]),
            active_default_holiday_calendar_count=int(
                row["active_default_holiday_calendar_count"] or 0
            ),
            has_active_leave_type_without_effective_policy=bool(
                row["has_active_leave_type_without_effective_policy"]
            ),
            active_document_type_count=int(row["active_document_type_count"] or 0),
            current_published_privacy_notice_count=int(
                row["current_published_privacy_notice_count"] or 0
            ),
        )

    def _items(
        self,
        *,
        evaluated_at: datetime,
        enabled: dict[FeatureFlagKey, bool],
        facts: _ReadinessFacts,
    ) -> list[TenantReadinessItemRead]:
        leave_state = TenantReadinessItemState.NOT_APPLICABLE
        if enabled[FeatureFlagKey.LEAVE]:
            leave_state = _state(
                facts.has_active_leave_type
                and facts.active_default_holiday_calendar_count == 1
                and not facts.has_active_leave_type_without_effective_policy
            )

        document_state = TenantReadinessItemState.NOT_APPLICABLE
        if enabled[FeatureFlagKey.DOCUMENTS]:
            document_state = _state(
                facts.active_document_type_count > 0 and self._document_runtime_is_suitable()
            )

        notification_state = (
            TenantReadinessItemState.ACTION_REQUIRED
            if enabled[FeatureFlagKey.NOTIFICATIONS]
            else TenantReadinessItemState.NOT_APPLICABLE
        )

        return [
            _item(
                key=TenantReadinessItemKey.DEFAULT_LEGAL_ENTITY,
                state=_state(facts.active_default_legal_entity_count == 1),
                count=facts.active_default_legal_entity_count,
                remediation_route="/organization",
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.ORGANIZATION_STRUCTURE,
                state=_state(facts.has_active_department and facts.has_active_position),
                count=None,
                remediation_route="/organization",
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.ACTIVE_TENANT_ADMINISTRATOR,
                state=_state(facts.active_tenant_administrator_count > 0),
                count=facts.active_tenant_administrator_count,
                remediation_route="/users",
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.EMPLOYEE_MASTER_DATA,
                state=_state(facts.active_employee_count > 0),
                count=facts.active_employee_count,
                remediation_route="/employees",
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.LEAVE_CONFIGURATION,
                state=leave_state,
                count=None,
                remediation_route="/leave/admin",
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.DOCUMENT_CONFIGURATION,
                state=document_state,
                count=facts.active_document_type_count,
                remediation_route=(
                    "/document-types" if facts.active_document_type_count == 0 else None
                ),
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.PRIVACY_NOTICE,
                state=_state(facts.current_published_privacy_notice_count > 0),
                count=facts.current_published_privacy_notice_count,
                remediation_route="/privacy/manage",
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.FEATURE_DEPENDENCIES,
                state=_state(_feature_dependencies_are_coherent(enabled)),
                count=None,
                remediation_route=None,
                evaluated_at=evaluated_at,
            ),
            _item(
                key=TenantReadinessItemKey.NOTIFICATION_DELIVERY,
                state=notification_state,
                count=None,
                remediation_route=None,
                evaluated_at=evaluated_at,
            ),
        ]

    def _document_runtime_is_suitable(self) -> bool:
        if not isinstance(self.document_runtime, DocumentRuntime):
            return False
        if self.settings.environment in {"local", "dev", "test"}:
            return True
        return (
            self.settings.document_storage_backend == "s3"
            and self.settings.document_scanner_backend == "clamav"
        )


def _state(ready: bool) -> TenantReadinessItemState:
    return TenantReadinessItemState.READY if ready else TenantReadinessItemState.ACTION_REQUIRED


def _feature_dependencies_are_coherent(
    enabled: dict[FeatureFlagKey, bool],
) -> bool:
    return all(
        not enabled[source] or enabled[dependency]
        for source, dependency in (
            (FeatureFlagKey.DOCUMENTS, FeatureFlagKey.EMPLOYEES),
            (FeatureFlagKey.LEAVE, FeatureFlagKey.EMPLOYEES),
            (FeatureFlagKey.SELF_SERVICE, FeatureFlagKey.EMPLOYEES),
            (FeatureFlagKey.REPORTING, FeatureFlagKey.EMPLOYEES),
            (FeatureFlagKey.NOTIFICATIONS, FeatureFlagKey.SELF_SERVICE),
        )
    )


def _item(
    *,
    key: TenantReadinessItemKey,
    state: TenantReadinessItemState,
    count: int | None,
    remediation_route: str | None,
    evaluated_at: datetime,
) -> TenantReadinessItemRead:
    return TenantReadinessItemRead(
        key=key,
        state=state,
        count=count,
        remediation_route=remediation_route,
        evaluated_at=evaluated_at,
    )


__all__ = ["TenantReadinessService"]
