"""Tenant-isolated privacy notices, consent evidence, and retention inventory."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.authorization import Permission, RolePermission, UserRole
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.identity import MembershipStatus, TenantMembership
from app.models.leave_request import LeaveRequest
from app.models.privacy import (
    PrivacyConsentAction,
    PrivacyConsentEvent,
    PrivacyConsentPurpose,
    PrivacyConsentState,
    PrivacyNotice,
    PrivacyNoticeAcknowledgement,
    PrivacyNoticeKind,
    PrivacyNoticeStatus,
    RetentionAnchor,
    RetentionDataCategory,
    RetentionPolicy,
)
from app.models.tenant import Tenant
from app.models.user import User, UserStatus
from app.platform.audit import (
    AuditActorType,
    AuditCategory,
    AuditContext,
    AuditDataClassification,
    AuditEventDraft,
    AuditEventType,
    AuditResult,
    AuditScopeType,
    AuditVisibilityClass,
)
from app.platform.request_context import RequestContext
from app.schemas.privacy import (
    PRIVACY_CONSENT_HISTORY_LIMIT,
    PRIVACY_CONSENT_PURPOSE_LIMIT,
    RETENTION_POLICY_LIMIT,
    ConsentCenterRead,
    ConsentEventRead,
    ConsentPurposeStateRead,
    EmployeePrivacyNoticeDetailRead,
    EmployeePrivacyNoticeRead,
    PrivacyNoticeAcknowledge,
    PrivacyNoticeCreate,
    PrivacyNoticeDetailRead,
    PrivacyNoticeSummaryRead,
    PrivacyNoticeUpdate,
    RetentionDryRunItemRead,
    RetentionDryRunRead,
    RetentionDryRunRequest,
    RetentionPolicyCreate,
    RetentionPolicyRead,
    RetentionPolicyUpdate,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.phase7_access import (
    Phase7ConflictError,
    Phase7NotFoundError,
    Phase7ValidationError,
    Phase7VersionConflictError,
)

PRIVACY_NOTICE_READ_PERMISSION = "privacy_notice:read:own"

_ANCHOR_BY_CATEGORY = {
    RetentionDataCategory.EMPLOYEE_RECORDS.value: RetentionAnchor.EMPLOYMENT_END_DATE.value,
    RetentionDataCategory.EMPLOYEE_DOCUMENTS.value: RetentionAnchor.ARCHIVED_AT.value,
    RetentionDataCategory.LEAVE_REQUESTS.value: RetentionAnchor.CREATED_AT.value,
    RetentionDataCategory.AUDIT_EVENTS.value: RetentionAnchor.OCCURRED_AT.value,
}


class PrivacyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = SqlAlchemyAuditRecorder(session)

    async def current_employee_notice(
        self,
        *,
        request_context: RequestContext,
    ) -> EmployeePrivacyNoticeRead:
        tenant_id, membership_id, actor_id = _own_context(request_context)
        notice = await self.session.scalar(
            select(PrivacyNotice)
            .where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
                PrivacyNotice.status == PrivacyNoticeStatus.PUBLISHED.value,
            )
            .order_by(PrivacyNotice.notice_version.desc(), PrivacyNotice.id.desc())
            .limit(1)
        )
        if notice is None:
            return EmployeePrivacyNoticeRead(notice=None, acknowledged_at=None)
        acknowledgement = await self.session.scalar(
            select(PrivacyNoticeAcknowledgement).where(
                PrivacyNoticeAcknowledgement.tenant_id == tenant_id,
                PrivacyNoticeAcknowledgement.notice_id == notice.id,
                PrivacyNoticeAcknowledgement.user_id == actor_id,
                PrivacyNoticeAcknowledgement.membership_id == membership_id,
            )
        )
        return EmployeePrivacyNoticeRead(
            notice=_employee_notice_detail(notice),
            acknowledged_at=(
                _aware(acknowledgement.acknowledged_at)
                if acknowledgement is not None
                else None
            ),
        )

    async def acknowledge_notice(
        self,
        *,
        request_context: RequestContext,
        payload: PrivacyNoticeAcknowledge,
    ) -> EmployeePrivacyNoticeRead:
        tenant_id, membership_id, actor_id = _own_context(request_context)
        await _lock_actor_resource(
            self.session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            resource_id=payload.notice_id,
            namespace="privacy-acknowledgement",
        )
        notice = await self.session.scalar(
            select(PrivacyNotice).where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.id == payload.notice_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
                PrivacyNotice.content_hash == payload.notice_content_hash,
                PrivacyNotice.status.in_(
                    (
                        PrivacyNoticeStatus.PUBLISHED.value,
                        PrivacyNoticeStatus.SUPERSEDED.value,
                    )
                ),
            )
        )
        if notice is None:
            raise Phase7NotFoundError

        acknowledgement = await self.session.scalar(
            select(PrivacyNoticeAcknowledgement).where(
                PrivacyNoticeAcknowledgement.tenant_id == tenant_id,
                PrivacyNoticeAcknowledgement.notice_id == notice.id,
                PrivacyNoticeAcknowledgement.user_id == actor_id,
                PrivacyNoticeAcknowledgement.membership_id == membership_id,
            )
        )
        if acknowledgement is None:
            now = datetime.now(UTC)
            acknowledgement = PrivacyNoticeAcknowledgement(
                id=uuid5(
                    NAMESPACE_URL,
                    f"wealthy-falcon:privacy-ack:{tenant_id}:{notice.id}:{actor_id}",
                ),
                tenant_id=tenant_id,
                notice_id=notice.id,
                notice_version=notice.notice_version,
                notice_content_hash=notice.content_hash,
                user_id=actor_id,
                membership_id=membership_id,
                acknowledged_at=now,
                evidence_request_sha256=_sha256_text(request_context.request_id),
                evidence_session_sha256=(
                    _sha256_text(str(request_context.session_id))
                    if request_context.session_id is not None
                    else None
                ),
            )
            self.session.add(acknowledgement)
            await self.session.flush()
            await self._audit_event(
                request_context,
                event_type=AuditEventType.PRIVACY_NOTICE_ACKNOWLEDGED,
                resource_type="privacy_notice",
                resource_id=notice.id,
                action="acknowledge",
                changed_fields=("acknowledged_at",),
                metadata={
                    "notice_kind": notice.kind,
                    "notice_version": notice.notice_version,
                    "notice_content_hash": notice.content_hash,
                    "membership_id": membership_id,
                },
            )
        return EmployeePrivacyNoticeRead(
            notice=_employee_notice_detail(notice),
            acknowledged_at=_aware(acknowledgement.acknowledged_at),
        )

    async def consent_center(
        self,
        *,
        request_context: RequestContext,
    ) -> ConsentCenterRead:
        tenant_id, membership_id, actor_id = _own_context(request_context)
        rows = (
            await self.session.execute(
                select(PrivacyConsentPurpose, PrivacyConsentState)
                .outerjoin(
                    PrivacyConsentState,
                    and_(
                        PrivacyConsentState.tenant_id == PrivacyConsentPurpose.tenant_id,
                        PrivacyConsentState.purpose_id == PrivacyConsentPurpose.id,
                        PrivacyConsentState.user_id == actor_id,
                        PrivacyConsentState.membership_id == membership_id,
                    ),
                )
                .where(
                    PrivacyConsentPurpose.tenant_id == tenant_id,
                    or_(
                        PrivacyConsentPurpose.is_active.is_(True),
                        PrivacyConsentState.id.is_not(None),
                        exists(
                            select(PrivacyConsentEvent.id).where(
                                PrivacyConsentEvent.tenant_id
                                == PrivacyConsentPurpose.tenant_id,
                                PrivacyConsentEvent.purpose_id == PrivacyConsentPurpose.id,
                                PrivacyConsentEvent.user_id == actor_id,
                                PrivacyConsentEvent.membership_id == membership_id,
                            )
                        ),
                    ),
                )
                .order_by(
                    PrivacyConsentPurpose.code,
                    PrivacyConsentPurpose.version.desc(),
                    PrivacyConsentPurpose.id,
                )
                .limit(PRIVACY_CONSENT_PURPOSE_LIMIT)
            )
        ).all()
        histories = await self._consent_histories(
            tenant_id=tenant_id,
            membership_id=membership_id,
            actor_id=actor_id,
            purpose_ids=tuple(purpose.id for purpose, _state in rows),
        )
        return ConsentCenterRead(
            purposes=[
                _consent_state_read(
                    purpose,
                    state,
                    history=histories.get(purpose.id, []),
                )
                for purpose, state in rows
            ]
        )

    async def transition_consent(
        self,
        *,
        request_context: RequestContext,
        purpose_id: UUID,
        action: PrivacyConsentAction,
    ) -> ConsentPurposeStateRead:
        tenant_id, membership_id, actor_id = _own_context(request_context)
        await _lock_actor_resource(
            self.session,
            tenant_id=tenant_id,
            membership_id=membership_id,
            resource_id=purpose_id,
            namespace="privacy-consent",
        )
        purpose = await self.session.scalar(
            select(PrivacyConsentPurpose).where(
                PrivacyConsentPurpose.tenant_id == tenant_id,
                PrivacyConsentPurpose.id == purpose_id,
            )
        )
        if purpose is None:
            raise Phase7NotFoundError
        state = await self.session.scalar(
            select(PrivacyConsentState)
            .where(
                PrivacyConsentState.tenant_id == tenant_id,
                PrivacyConsentState.purpose_id == purpose_id,
                PrivacyConsentState.user_id == actor_id,
                PrivacyConsentState.membership_id == membership_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        desired_granted = action is PrivacyConsentAction.GRANT
        if (
            desired_granted
            and not purpose.is_active
            and (state is None or not state.granted)
        ):
            raise Phase7NotFoundError
        changed = state is None and desired_granted
        changed = changed or (state is not None and state.granted != desired_granted)
        if changed:
            now = datetime.now(UTC)
            if state is None:
                state = PrivacyConsentState(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"wealthy-falcon:privacy-consent-state:{tenant_id}:"
                        f"{purpose.id}:{actor_id}",
                    ),
                    tenant_id=tenant_id,
                    purpose_id=purpose.id,
                    user_id=actor_id,
                    membership_id=membership_id,
                    granted=desired_granted,
                    version=1,
                )
                self.session.add(state)
            else:
                state.granted = desired_granted
                state.updated_at = now
            event = PrivacyConsentEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                purpose_id=purpose.id,
                purpose_version=purpose.version,
                user_id=actor_id,
                membership_id=membership_id,
                action=action.value,
                occurred_at=now,
            )
            self.session.add(event)
            await self.session.flush()
            await self.session.refresh(state)
            await self._audit_event(
                request_context,
                event_type=(
                    AuditEventType.PRIVACY_CONSENT_GRANTED
                    if desired_granted
                    else AuditEventType.PRIVACY_CONSENT_WITHDRAWN
                ),
                resource_type="privacy_consent_purpose",
                resource_id=purpose.id,
                action=action.value,
                changed_fields=("granted", "version"),
                metadata={
                    "purpose_id": purpose.id,
                    "purpose_version": purpose.version,
                },
                anonymize_actor=True,
            )
        histories = await self._consent_histories(
            tenant_id=tenant_id,
            membership_id=membership_id,
            actor_id=actor_id,
            purpose_ids=(purpose.id,),
        )
        return _consent_state_read(
            purpose,
            state,
            history=histories.get(purpose.id, []),
        )

    async def list_notices(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> list[PrivacyNoticeSummaryRead]:
        notices = list(
            await self.session.scalars(
                select(PrivacyNotice)
                .where(
                    PrivacyNotice.tenant_id == tenant_id,
                    PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
                )
                .order_by(
                    PrivacyNotice.notice_version.desc(),
                    PrivacyNotice.created_at.desc(),
                    PrivacyNotice.id.desc(),
                )
                .limit(limit)
            )
        )
        counts, eligible_count = await self._notice_counts(
            tenant_id,
            tuple(notice.id for notice in notices),
        )
        return [
            _notice_summary(
                notice,
                acknowledged_count=counts.get(notice.id, 0),
                eligible_count=eligible_count,
            )
            for notice in notices
        ]

    async def get_notice(
        self,
        *,
        tenant_id: UUID,
        notice_id: UUID,
    ) -> PrivacyNoticeDetailRead:
        notice = await self.session.scalar(
            select(PrivacyNotice).where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.id == notice_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
            )
        )
        if notice is None:
            raise Phase7NotFoundError
        return await self._notice_detail(notice)

    async def create_notice(
        self,
        *,
        request_context: RequestContext,
        payload: PrivacyNoticeCreate,
    ) -> PrivacyNoticeDetailRead:
        tenant_id, _membership_id, actor_id = _own_context(request_context)
        await self._lock_tenant(tenant_id)
        highest_version = await self.session.scalar(
            select(func.max(PrivacyNotice.notice_version)).where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
            )
        )
        notice = PrivacyNotice(
            id=uuid4(),
            tenant_id=tenant_id,
            kind=PrivacyNoticeKind.EMPLOYEE.value,
            locale=payload.locale,
            notice_version=int(highest_version or 0) + 1,
            revision=1,
            title=payload.title,
            body=payload.body,
            content_hash=_sha256_text(payload.body),
            status=PrivacyNoticeStatus.DRAFT.value,
            created_by_user_id=actor_id,
            published_by_user_id=None,
            published_at=None,
        )
        self.session.add(notice)
        await self.session.flush()
        await self.session.refresh(notice)
        return await self._notice_detail(notice)

    async def update_notice(
        self,
        *,
        request_context: RequestContext,
        notice_id: UUID,
        payload: PrivacyNoticeUpdate,
    ) -> PrivacyNoticeDetailRead:
        tenant_id, _membership_id, _actor_id = _own_context(request_context)
        notice = await self._locked_notice(tenant_id, notice_id)
        if notice.status != PrivacyNoticeStatus.DRAFT.value:
            raise Phase7ConflictError
        if notice.revision != payload.expected_revision:
            raise Phase7VersionConflictError
        if payload.title is not None:
            notice.title = payload.title
        if payload.body is not None:
            notice.body = payload.body
            notice.content_hash = _sha256_text(payload.body)
        if payload.locale is not None:
            notice.locale = payload.locale
        notice.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(notice)
        return await self._notice_detail(notice)

    async def publish_notice(
        self,
        *,
        request_context: RequestContext,
        notice_id: UUID,
        expected_revision: int,
    ) -> PrivacyNoticeDetailRead:
        tenant_id, _membership_id, actor_id = _own_context(request_context)
        await self._lock_tenant(tenant_id)
        notice = await self._locked_notice(tenant_id, notice_id)
        if notice.status in {
            PrivacyNoticeStatus.PUBLISHED.value,
            PrivacyNoticeStatus.SUPERSEDED.value,
        }:
            return await self._notice_detail(notice)
        if notice.status != PrivacyNoticeStatus.DRAFT.value:
            raise Phase7ConflictError
        if notice.revision != expected_revision:
            raise Phase7VersionConflictError
        current = await self.session.scalar(
            select(PrivacyNotice)
            .where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
                PrivacyNotice.status == PrivacyNoticeStatus.PUBLISHED.value,
                PrivacyNotice.id != notice.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if current is not None and notice.notice_version <= current.notice_version:
            raise Phase7ConflictError
        now = datetime.now(UTC)
        if current is not None:
            current.status = PrivacyNoticeStatus.SUPERSEDED.value
            # The current-published partial unique index is immediate. Persist the old
            # version's status transition before promoting the newer draft.
            await self.session.flush()
        notice.status = PrivacyNoticeStatus.PUBLISHED.value
        notice.published_by_user_id = actor_id
        notice.published_at = now
        notice.updated_at = now
        await self.session.flush()
        await self.session.refresh(notice)
        await self._audit_event(
            request_context,
            event_type=AuditEventType.PRIVACY_NOTICE_PUBLISHED,
            resource_type="privacy_notice",
            resource_id=notice.id,
            action="publish",
            changed_fields=("status", "published_at", "revision"),
            metadata={
                "notice_kind": notice.kind,
                "notice_version": notice.notice_version,
                "notice_content_hash": notice.content_hash,
            },
        )
        return await self._notice_detail(notice)

    async def list_retention_policies(self, *, tenant_id: UUID) -> list[RetentionPolicyRead]:
        policies = list(
            await self.session.scalars(
                select(RetentionPolicy)
                .where(RetentionPolicy.tenant_id == tenant_id)
                .order_by(RetentionPolicy.data_category, RetentionPolicy.id)
                .limit(RETENTION_POLICY_LIMIT)
            )
        )
        return [_retention_policy_read(policy) for policy in policies]

    async def create_retention_policy(
        self,
        *,
        request_context: RequestContext,
        payload: RetentionPolicyCreate,
    ) -> RetentionPolicyRead:
        tenant_id, _membership_id, actor_id = _own_context(request_context)
        await self._lock_tenant(tenant_id)
        existing_id = await self.session.scalar(
            select(RetentionPolicy.id).where(
                RetentionPolicy.tenant_id == tenant_id,
                RetentionPolicy.data_category == payload.data_category.value,
            )
        )
        if existing_id is not None:
            raise Phase7ConflictError
        policy = RetentionPolicy(
            id=uuid4(),
            tenant_id=tenant_id,
            data_category=payload.data_category.value,
            legal_basis_note=payload.legal_basis_note,
            retention_days=payload.retention_days,
            anchor=payload.anchor.value,
            action=payload.action.value,
            status=payload.status.value,
            version=1,
            created_by_user_id=actor_id,
            updated_by_user_id=actor_id,
        )
        self.session.add(policy)
        await self.session.flush()
        await self.session.refresh(policy)
        await self._audit_retention_mutation(
            request_context,
            policy=policy,
            action="create",
            changed_fields=(
                "data_category",
                "legal_basis_note",
                "retention_days",
                "anchor",
                "action",
                "status",
                "version",
            ),
        )
        return _retention_policy_read(policy)

    async def update_retention_policy(
        self,
        *,
        request_context: RequestContext,
        policy_id: UUID,
        payload: RetentionPolicyUpdate,
    ) -> RetentionPolicyRead:
        tenant_id, _membership_id, actor_id = _own_context(request_context)
        await self._lock_tenant(tenant_id)
        policy = await self.session.scalar(
            select(RetentionPolicy)
            .where(
                RetentionPolicy.tenant_id == tenant_id,
                RetentionPolicy.id == policy_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if policy is None:
            raise Phase7NotFoundError
        if policy.version != payload.expected_version:
            raise Phase7VersionConflictError
        data_category = (
            payload.data_category.value
            if payload.data_category is not None
            else policy.data_category
        )
        anchor = payload.anchor.value if payload.anchor is not None else policy.anchor
        if _ANCHOR_BY_CATEGORY.get(data_category) != anchor:
            raise Phase7ValidationError("Retention anchor does not match the data category")
        conflicting_policy_id = await self.session.scalar(
            select(RetentionPolicy.id).where(
                RetentionPolicy.tenant_id == tenant_id,
                RetentionPolicy.data_category == data_category,
                RetentionPolicy.id != policy.id,
            )
        )
        if conflicting_policy_id is not None:
            raise Phase7ConflictError
        for field_name in (
            "legal_basis_note",
            "retention_days",
            "status",
        ):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(policy, field_name, value.value if hasattr(value, "value") else value)
        if payload.data_category is not None:
            policy.data_category = payload.data_category.value
        if payload.anchor is not None:
            policy.anchor = payload.anchor.value
        if payload.action is not None:
            policy.action = payload.action.value
        policy.updated_by_user_id = actor_id
        policy.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(policy)
        changed_fields = tuple(
            sorted((payload.model_fields_set - {"expected_version"}) | {"version"})
        )
        await self._audit_retention_mutation(
            request_context,
            policy=policy,
            action="update",
            changed_fields=changed_fields,
        )
        return _retention_policy_read(policy)

    async def retention_dry_run(
        self,
        *,
        request_context: RequestContext,
        payload: RetentionDryRunRequest,
    ) -> RetentionDryRunRead:
        tenant_id, _membership_id, _actor_id = _own_context(request_context)
        statement = select(RetentionPolicy).where(RetentionPolicy.tenant_id == tenant_id)
        if payload.policy_ids:
            statement = statement.where(RetentionPolicy.id.in_(payload.policy_ids))
        policies = list(
            await self.session.scalars(
                statement.order_by(RetentionPolicy.data_category, RetentionPolicy.id).limit(
                    RETENTION_POLICY_LIMIT + 1
                )
            )
        )
        if len(policies) > RETENTION_POLICY_LIMIT:
            raise Phase7ValidationError("Retention policy selection exceeds the limit")
        if payload.policy_ids and {policy.id for policy in policies} != set(payload.policy_ids):
            raise Phase7NotFoundError

        as_of = datetime.now(UTC)
        items: list[RetentionDryRunItemRead] = []
        for policy in policies:
            cutoff = as_of - timedelta(days=policy.retention_days)
            count = await self._retention_count(
                tenant_id=tenant_id,
                data_category=policy.data_category,
                cutoff=cutoff,
            )
            item = RetentionDryRunItemRead(
                policy_id=policy.id,
                data_category=policy.data_category,
                retention_days=policy.retention_days,
                anchor=policy.anchor,
                action=policy.action,
                status=policy.status,
                policy_version=policy.version,
                cutoff_at=cutoff,
                count=count,
            )
            items.append(item)
            await self._audit_event(
                request_context,
                event_type=AuditEventType.RETENTION_DRY_RUN,
                resource_type="retention_policy",
                resource_id=policy.id,
                action="dry_run",
                changed_fields=(),
                metadata={
                    "data_category": policy.data_category,
                    "retention_action": policy.action,
                    "policy_version": policy.version,
                    "count": count,
                },
            )
        return RetentionDryRunRead(as_of=as_of, items=items)

    async def _locked_notice(self, tenant_id: UUID, notice_id: UUID) -> PrivacyNotice:
        notice = await self.session.scalar(
            select(PrivacyNotice)
            .where(
                PrivacyNotice.tenant_id == tenant_id,
                PrivacyNotice.id == notice_id,
                PrivacyNotice.kind == PrivacyNoticeKind.EMPLOYEE.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if notice is None:
            raise Phase7NotFoundError
        return notice

    async def _lock_tenant(self, tenant_id: UUID) -> None:
        locked_id = await self.session.scalar(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        )
        if locked_id is None:
            raise Phase7NotFoundError

    async def _notice_detail(self, notice: PrivacyNotice) -> PrivacyNoticeDetailRead:
        counts, eligible_count = await self._notice_counts(notice.tenant_id, (notice.id,))
        return PrivacyNoticeDetailRead(
            **_notice_summary(
                notice,
                acknowledged_count=counts.get(notice.id, 0),
                eligible_count=eligible_count,
            ).model_dump(),
            body=notice.body,
        )

    async def _notice_counts(
        self,
        tenant_id: UUID,
        notice_ids: tuple[UUID, ...],
    ) -> tuple[dict[UUID, int], int]:
        if not notice_ids:
            return {}, 0
        if self.session.get_bind().dialect.name == "postgresql":
            rows = (
                await self.session.execute(
                    text(
                        """
                        SELECT notice_id, acknowledged_count, eligible_count
                        FROM p9_privacy_notice_coverage(CAST(:notice_ids AS uuid[]))
                        """
                    ),
                    {"notice_ids": list(notice_ids)},
                )
            ).mappings()
            counts: dict[UUID, int] = {}
            eligible_count = 0
            for row in rows:
                counts[row["notice_id"]] = int(row["acknowledged_count"])
                eligible_count = max(eligible_count, int(row["eligible_count"]))
            return counts, eligible_count

        counts = {}
        if notice_ids:
            rows = (
                await self.session.execute(
                    select(
                        PrivacyNoticeAcknowledgement.notice_id,
                        func.count(
                            func.distinct(PrivacyNoticeAcknowledgement.membership_id)
                        ),
                    )
                    .join(
                        User,
                        and_(
                            User.tenant_id == PrivacyNoticeAcknowledgement.tenant_id,
                            User.id == PrivacyNoticeAcknowledgement.user_id,
                        ),
                    )
                    .join(
                        TenantMembership,
                        and_(
                            TenantMembership.tenant_id
                            == PrivacyNoticeAcknowledgement.tenant_id,
                            TenantMembership.id
                            == PrivacyNoticeAcknowledgement.membership_id,
                            TenantMembership.legacy_user_id
                            == PrivacyNoticeAcknowledgement.user_id,
                        ),
                    )
                    .where(
                        PrivacyNoticeAcknowledgement.tenant_id == tenant_id,
                        PrivacyNoticeAcknowledgement.notice_id.in_(notice_ids),
                        User.status == UserStatus.ACTIVE.value,
                        TenantMembership.status == MembershipStatus.ACTIVE.value,
                        TenantMembership.permission_version == User.permission_version,
                        exists(
                            select(UserRole.user_id)
                            .join(
                                RolePermission,
                                RolePermission.role_id == UserRole.role_id,
                            )
                            .join(Permission, Permission.id == RolePermission.permission_id)
                            .where(
                                UserRole.tenant_id == tenant_id,
                                UserRole.user_id == User.id,
                                UserRole.active.is_(True),
                                Permission.code == PRIVACY_NOTICE_READ_PERMISSION,
                            )
                        ),
                    )
                    .group_by(PrivacyNoticeAcknowledgement.notice_id)
                )
            ).all()
            counts = {notice_id: int(count) for notice_id, count in rows}
        eligible_count = await self.session.scalar(
            select(func.count(func.distinct(TenantMembership.id)))
            .select_from(User)
            .join(
                TenantMembership,
                and_(
                    TenantMembership.tenant_id == User.tenant_id,
                    TenantMembership.legacy_user_id == User.id,
                ),
            )
            .where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE.value,
                TenantMembership.status == MembershipStatus.ACTIVE.value,
                TenantMembership.permission_version == User.permission_version,
                exists(
                    select(UserRole.user_id)
                    .join(RolePermission, RolePermission.role_id == UserRole.role_id)
                    .join(Permission, Permission.id == RolePermission.permission_id)
                    .where(
                        UserRole.tenant_id == tenant_id,
                        UserRole.user_id == User.id,
                        UserRole.active.is_(True),
                        Permission.code == PRIVACY_NOTICE_READ_PERMISSION,
                    )
                ),
            )
        )
        return counts, int(eligible_count or 0)

    async def _consent_histories(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        actor_id: UUID,
        purpose_ids: tuple[UUID, ...],
    ) -> dict[UUID, list[ConsentEventRead]]:
        if not purpose_ids:
            return {}
        rank = func.row_number().over(
            partition_by=PrivacyConsentEvent.purpose_id,
            order_by=(
                PrivacyConsentEvent.occurred_at.desc(),
                PrivacyConsentEvent.id.desc(),
            ),
        ).label("history_rank")
        ranked = (
            select(
                PrivacyConsentEvent.id.label("id"),
                PrivacyConsentEvent.purpose_id.label("purpose_id"),
                PrivacyConsentEvent.action.label("action"),
                PrivacyConsentEvent.purpose_version.label("purpose_version"),
                PrivacyConsentEvent.occurred_at.label("occurred_at"),
                rank,
            )
            .where(
                PrivacyConsentEvent.tenant_id == tenant_id,
                PrivacyConsentEvent.user_id == actor_id,
                PrivacyConsentEvent.membership_id == membership_id,
                PrivacyConsentEvent.purpose_id.in_(purpose_ids),
            )
            .subquery()
        )
        rows = (
            await self.session.execute(
                select(ranked)
                .where(ranked.c.history_rank <= PRIVACY_CONSENT_HISTORY_LIMIT)
                .order_by(
                    ranked.c.purpose_id,
                    ranked.c.occurred_at.desc(),
                    ranked.c.id.desc(),
                )
                .limit(len(purpose_ids) * PRIVACY_CONSENT_HISTORY_LIMIT)
            )
        ).mappings()
        histories: dict[UUID, list[ConsentEventRead]] = defaultdict(list)
        for row in rows:
            histories[row["purpose_id"]].append(
                ConsentEventRead(
                    id=row["id"],
                    action=row["action"],
                    purpose_version=row["purpose_version"],
                    occurred_at=_aware(row["occurred_at"]),
                )
            )
        return dict(histories)

    async def _retention_count(
        self,
        *,
        tenant_id: UUID,
        data_category: str,
        cutoff: datetime,
    ) -> int:
        if data_category == RetentionDataCategory.EMPLOYEE_RECORDS.value:
            statement = (
                select(func.count())
                .select_from(Employee)
                .where(
                    Employee.tenant_id == tenant_id,
                    Employee.employment_end_date.is_not(None),
                    Employee.employment_end_date <= cutoff.date(),
                )
            )
        elif data_category == RetentionDataCategory.EMPLOYEE_DOCUMENTS.value:
            statement = (
                select(func.count())
                .select_from(EmployeeDocument)
                .where(
                    EmployeeDocument.tenant_id == tenant_id,
                    EmployeeDocument.archived_at.is_not(None),
                    EmployeeDocument.archived_at <= cutoff,
                )
            )
        elif data_category == RetentionDataCategory.LEAVE_REQUESTS.value:
            statement = (
                select(func.count())
                .select_from(LeaveRequest)
                .where(
                    LeaveRequest.tenant_id == tenant_id,
                    LeaveRequest.created_at <= cutoff,
                )
            )
        elif data_category == RetentionDataCategory.AUDIT_EVENTS.value:
            statement = (
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.occurred_at <= cutoff,
                )
            )
        else:  # pragma: no cover - model and schema are closed enums
            raise Phase7ValidationError("Retention data category is unsupported")
        return int(await self.session.scalar(statement) or 0)

    async def _audit_retention_mutation(
        self,
        request_context: RequestContext,
        *,
        policy: RetentionPolicy,
        action: str,
        changed_fields: tuple[str, ...],
    ) -> None:
        await self._audit_event(
            request_context,
            event_type=AuditEventType.RETENTION_POLICY_MUTATED,
            resource_type="retention_policy",
            resource_id=policy.id,
            action=action,
            changed_fields=changed_fields,
            metadata={
                "data_category": policy.data_category,
                "retention_action": policy.action,
                "policy_version": policy.version,
            },
        )

    async def _audit_event(
        self,
        request_context: RequestContext,
        *,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: UUID,
        action: str,
        changed_fields: tuple[str, ...],
        metadata: dict[str, object],
        anonymize_actor: bool = False,
    ) -> None:
        await self.audit.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=(
                    AuditActorType.SYSTEM if anonymize_actor else AuditActorType.USER
                ),
                actor_user_id=None if anonymize_actor else request_context.actor_id,
                session_id=None if anonymize_actor else request_context.session_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                result=AuditResult.SUCCESS,
                changed_fields=changed_fields,
                metadata=metadata,
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                context=AuditContext.from_request_context(request_context),
            )
        )


async def _lock_actor_resource(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    resource_id: UUID,
    namespace: str,
) -> None:
    """Serialize absent-row own transitions without locking immutable reference rows."""

    if session.get_bind().dialect.name != "postgresql":
        return
    material = f"{namespace}:{tenant_id}:{membership_id}:{resource_id}".encode()
    lock_key = int.from_bytes(sha256(material).digest()[:8], byteorder="big", signed=True)
    await session.execute(
        text("SELECT pg_catalog.pg_advisory_xact_lock(CAST(:lock_key AS bigint))"),
        {"lock_key": lock_key},
    )


def _notice_summary(
    notice: PrivacyNotice,
    *,
    acknowledged_count: int,
    eligible_count: int,
) -> PrivacyNoticeSummaryRead:
    return PrivacyNoticeSummaryRead(
        **_notice_version_values(notice),
        acknowledged_count=acknowledged_count,
        eligible_count=eligible_count,
    )


def _employee_notice_detail(notice: PrivacyNotice) -> EmployeePrivacyNoticeDetailRead:
    return EmployeePrivacyNoticeDetailRead(
        **_notice_version_values(notice),
        body=notice.body,
    )


def _notice_version_values(notice: PrivacyNotice) -> dict[str, object]:
    return {
        "id": notice.id,
        "notice_kind": notice.kind,
        "locale": notice.locale,
        "notice_version": notice.notice_version,
        "revision": notice.revision,
        "title": notice.title,
        "content_hash": notice.content_hash,
        "status": notice.status,
        "published_at": (
            _aware(notice.published_at) if notice.published_at is not None else None
        ),
        "created_at": _aware(notice.created_at),
        "updated_at": _aware(notice.updated_at),
    }


def _consent_state_read(
    purpose: PrivacyConsentPurpose,
    state: PrivacyConsentState | None,
    *,
    history: list[ConsentEventRead],
) -> ConsentPurposeStateRead:
    return ConsentPurposeStateRead(
        id=purpose.id,
        code=purpose.code,
        version=purpose.version,
        title=purpose.title,
        description=purpose.description,
        is_active=purpose.is_active,
        granted=state.granted if state is not None else False,
        state_version=state.version if state is not None else 0,
        updated_at=_aware(state.updated_at) if state is not None else None,
        history=history,
    )


def _retention_policy_read(policy: RetentionPolicy) -> RetentionPolicyRead:
    return RetentionPolicyRead(
        id=policy.id,
        data_category=policy.data_category,
        legal_basis_note=policy.legal_basis_note,
        retention_days=policy.retention_days,
        anchor=policy.anchor,
        action=policy.action,
        status=policy.status,
        version=policy.version,
        created_at=_aware(policy.created_at),
        updated_at=_aware(policy.updated_at),
    )


def _own_context(context: RequestContext) -> tuple[UUID, UUID, UUID]:
    if context.actor_id is None:
        raise RuntimeError("Privacy operations require an authenticated actor")
    return (
        context.require_tenant().tenant_id,
        context.require_membership(),
        context.actor_id,
    )


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["PRIVACY_NOTICE_READ_PERMISSION", "PrivacyService"]
