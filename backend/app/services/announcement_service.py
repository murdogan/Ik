"""Announcement lifecycle, audience snapshotting, and recipient consumption."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import (
    Announcement,
    AnnouncementBranchTarget,
    AnnouncementDepartmentTarget,
    AnnouncementRecipient,
    AnnouncementRoleTarget,
    AnnouncementStatus,
)
from app.models.authorization import Permission, Role, RolePermission, UserRole
from app.models.department import Department
from app.models.employee_account_link import EmployeeAccountLink
from app.models.employee_assignment import EmployeeAssignment
from app.models.identity import TenantMembership
from app.models.leave import OutboxEvent
from app.models.organization import Branch
from app.models.user import User
from app.modules.core.domain.feature_flags import FeatureFlagKey
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
from app.platform.pagination import CursorPage, InvalidCursorError, decode_cursor, encode_cursor
from app.platform.request_context import RequestContext
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementDetailRead,
    AnnouncementSummaryRead,
    AnnouncementTargetOption,
    AnnouncementTargetOptionsRead,
    AnnouncementTargets,
    AnnouncementUpdate,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.phase7_access import (
    Phase7ConflictError,
    Phase7NotFoundError,
    Phase7ValidationError,
    Phase7VersionConflictError,
    require_phase7_feature,
)

ANNOUNCEMENT_RECIPIENT_LIMIT = 500
_CURSOR_RESOURCE = "announcements_v1"


class AnnouncementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = SqlAlchemyAuditRecorder(session)

    async def create(
        self,
        *,
        request_context: RequestContext,
        payload: AnnouncementCreate,
    ) -> AnnouncementDetailRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._require_feature(tenant_id)
        await self._validate_targets(tenant_id, payload.targets)
        announcement = Announcement(
            id=uuid4(),
            tenant_id=tenant_id,
            title=payload.title,
            body=payload.body,
            is_critical=payload.is_critical,
            status=AnnouncementStatus.DRAFT.value,
            version=1,
            created_by_user_id=actor_id,
            published_by_user_id=None,
            published_at=None,
            archived_by_user_id=None,
            archived_at=None,
        )
        self.session.add(announcement)
        await self.session.flush()
        await self.session.refresh(announcement)
        await self._replace_targets(announcement, payload.targets)
        await self.session.flush()
        await self._audit(
            request_context,
            announcement=announcement,
            event_type=AuditEventType.ANNOUNCEMENT_CREATED,
            action="create",
            before_status=None,
            metadata={"after_status": announcement.status, "version": announcement.version},
            changed_fields=(
                "title",
                "text_changed",
                "is_critical",
                "targeting",
                "status",
                "version",
            ),
        )
        return await self._detail(announcement, recipient=None, include_targets=True)

    async def update(
        self,
        *,
        request_context: RequestContext,
        announcement_id: UUID,
        payload: AnnouncementUpdate,
    ) -> AnnouncementDetailRead:
        tenant_id, _ = _tenant_actor(request_context)
        await self._require_feature(tenant_id)
        announcement = await self._locked_draft(
            tenant_id,
            announcement_id,
            payload.expected_version,
        )
        if payload.targets is not None:
            await self._validate_targets(tenant_id, payload.targets)
        if payload.title is not None:
            announcement.title = payload.title
        if payload.body is not None:
            announcement.body = payload.body
        if payload.is_critical is not None:
            announcement.is_critical = payload.is_critical
        if payload.targets is not None:
            await self._replace_targets(announcement, payload.targets)
        announcement.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self._audit(
            request_context,
            announcement=announcement,
            event_type=AuditEventType.ANNOUNCEMENT_UPDATED,
            action="update",
            before_status=AnnouncementStatus.DRAFT.value,
            metadata={
                "before_status": AnnouncementStatus.DRAFT.value,
                "after_status": announcement.status,
                "version": announcement.version,
            },
            changed_fields=(
                tuple(
                    field
                    for field in ("title", "is_critical", "targeting", "version")
                    if field == "version"
                    or field in payload.model_fields_set
                    or (field == "targeting" and "targets" in payload.model_fields_set)
                )
                + (("text_changed",) if "body" in payload.model_fields_set else ())
            ),
        )
        return await self._detail(announcement, recipient=None, include_targets=True)

    async def publish(
        self,
        *,
        request_context: RequestContext,
        announcement_id: UUID,
        expected_version: int,
    ) -> AnnouncementDetailRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._require_feature(tenant_id)
        announcement = await self._locked_draft(tenant_id, announcement_id, expected_version)
        targets = await self._target_ids(tenant_id, announcement.id)
        await self._validate_targets(tenant_id, targets)
        recipient_ids = await self._recipient_ids(tenant_id, targets)
        if len(recipient_ids) > ANNOUNCEMENT_RECIPIENT_LIMIT:
            raise Phase7ValidationError(
                "Announcement audience exceeds the publication recipient limit"
            )
        now = datetime.now(UTC)
        announcement.status = AnnouncementStatus.PUBLISHED.value
        announcement.published_by_user_id = actor_id
        announcement.published_at = now
        announcement.updated_at = now
        await self.session.flush()
        for recipient_user_id in recipient_ids:
            self.session.add(
                AnnouncementRecipient(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"wealthy-falcon:announcement-recipient:{tenant_id}:"
                        f"{announcement.id}:{recipient_user_id}",
                    ),
                    tenant_id=tenant_id,
                    announcement_id=announcement.id,
                    recipient_user_id=recipient_user_id,
                    published_at=now,
                    read_at=None,
                    acknowledged_at=None,
                    version=1,
                )
            )
        self.session.add(
            OutboxEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                aggregate_type="announcement",
                aggregate_id=announcement.id,
                event_type="announcement.published",
                payload={
                    "announcement_id": str(announcement.id),
                    "critical": announcement.is_critical,
                },
                source_key=f"announcement.published:{announcement.id}",
                occurred_at=now,
            )
        )
        await self.session.flush()
        await self._audit(
            request_context,
            announcement=announcement,
            event_type=AuditEventType.ANNOUNCEMENT_PUBLISHED,
            action="publish",
            before_status=AnnouncementStatus.DRAFT.value,
            metadata={
                "before_status": AnnouncementStatus.DRAFT.value,
                "after_status": announcement.status,
                "recipient_count": len(recipient_ids),
                "version": announcement.version,
            },
            changed_fields=("status", "published_at", "version"),
        )
        return await self._detail(announcement, recipient=None, include_targets=True)

    async def archive(
        self,
        *,
        request_context: RequestContext,
        announcement_id: UUID,
        expected_version: int,
    ) -> AnnouncementDetailRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._require_feature(tenant_id)
        announcement = await self.session.scalar(
            select(Announcement)
            .where(
                Announcement.tenant_id == tenant_id,
                Announcement.id == announcement_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if announcement is None:
            raise Phase7NotFoundError
        if announcement.version != expected_version:
            raise Phase7VersionConflictError
        if announcement.status != AnnouncementStatus.PUBLISHED.value:
            raise Phase7ConflictError
        now = datetime.now(UTC)
        announcement.status = AnnouncementStatus.ARCHIVED.value
        announcement.archived_by_user_id = actor_id
        announcement.archived_at = now
        announcement.updated_at = now
        await self.session.flush()
        await self._audit(
            request_context,
            announcement=announcement,
            event_type=AuditEventType.ANNOUNCEMENT_ARCHIVED,
            action="archive",
            before_status=AnnouncementStatus.PUBLISHED.value,
            metadata={
                "before_status": AnnouncementStatus.PUBLISHED.value,
                "after_status": announcement.status,
                "version": announcement.version,
            },
            changed_fields=("status", "archived_at", "version"),
        )
        return await self._detail(announcement, recipient=None, include_targets=True)

    async def list_page(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        manage: bool,
        status: AnnouncementStatus | None,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[AnnouncementSummaryRead]:
        await self._require_feature(tenant_id)
        cursor_values = _decode_cursor(cursor, manage=manage, status=status)
        if manage:
            statement = select(Announcement, AnnouncementRecipient).outerjoin(
                AnnouncementRecipient,
                and_(
                    AnnouncementRecipient.tenant_id == Announcement.tenant_id,
                    AnnouncementRecipient.announcement_id == Announcement.id,
                    AnnouncementRecipient.recipient_user_id == actor_id,
                ),
            )
        else:
            statement = select(Announcement, AnnouncementRecipient).join(
                AnnouncementRecipient,
                and_(
                    AnnouncementRecipient.tenant_id == Announcement.tenant_id,
                    AnnouncementRecipient.announcement_id == Announcement.id,
                    AnnouncementRecipient.recipient_user_id == actor_id,
                ),
            )
        statement = statement.where(Announcement.tenant_id == tenant_id)
        if manage:
            if status is not None:
                statement = statement.where(Announcement.status == status.value)
        else:
            statement = statement.where(Announcement.status == AnnouncementStatus.PUBLISHED.value)
        if cursor_values is not None:
            created_at, announcement_id = cursor_values
            statement = statement.where(
                or_(
                    Announcement.created_at < created_at,
                    and_(Announcement.created_at == created_at, Announcement.id < announcement_id),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(Announcement.created_at.desc(), Announcement.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
        items = [
            self._summary(announcement, None if manage else recipient)
            for announcement, recipient in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = encode_cursor(
                _CURSOR_RESOURCE,
                {
                    "created_at": _aware(last.created_at).isoformat(),
                    "id": str(last.id),
                    "manage": "1" if manage else "0",
                    "status": status.value if status is not None else "",
                },
            )
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        announcement_id: UUID,
        manage: bool,
    ) -> AnnouncementDetailRead:
        await self._require_feature(tenant_id)
        if manage:
            row = (
                await self.session.execute(
                    select(Announcement, AnnouncementRecipient)
                    .outerjoin(
                        AnnouncementRecipient,
                        and_(
                            AnnouncementRecipient.tenant_id == Announcement.tenant_id,
                            AnnouncementRecipient.announcement_id == Announcement.id,
                            AnnouncementRecipient.recipient_user_id == actor_id,
                        ),
                    )
                    .where(
                        Announcement.tenant_id == tenant_id,
                        Announcement.id == announcement_id,
                    )
                    .limit(1)
                )
            ).one_or_none()
        else:
            row = (
                await self.session.execute(
                    select(Announcement, AnnouncementRecipient)
                    .join(
                        AnnouncementRecipient,
                        and_(
                            AnnouncementRecipient.tenant_id == Announcement.tenant_id,
                            AnnouncementRecipient.announcement_id == Announcement.id,
                            AnnouncementRecipient.recipient_user_id == actor_id,
                        ),
                    )
                    .where(
                        Announcement.tenant_id == tenant_id,
                        Announcement.id == announcement_id,
                        Announcement.status == AnnouncementStatus.PUBLISHED.value,
                    )
                    .limit(1)
                )
            ).one_or_none()
        if row is None:
            raise Phase7NotFoundError
        announcement, recipient = row
        return await self._detail(
            announcement,
            recipient=None if manage else recipient,
            include_targets=manage,
        )

    async def target_options(self, *, tenant_id: UUID) -> AnnouncementTargetOptionsRead:
        await self._require_feature(tenant_id)
        roles = list(
            await self.session.scalars(
                select(Role)
                .join(RolePermission, RolePermission.role_id == Role.id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(
                    Role.scope_type == "tenant",
                    Permission.code == "announcement:read:own",
                )
                .order_by(Role.name, Role.id)
                .limit(100)
            )
        )
        departments = list(
            await self.session.scalars(
                select(Department)
                .where(
                    Department.tenant_id == tenant_id,
                    Department.status == "active",
                )
                .order_by(Department.name, Department.id)
                .limit(100)
            )
        )
        branches = list(
            await self.session.scalars(
                select(Branch)
                .where(Branch.tenant_id == tenant_id, Branch.status == "active")
                .order_by(Branch.name, Branch.id)
                .limit(100)
            )
        )
        return AnnouncementTargetOptionsRead(
            roles=[AnnouncementTargetOption(id=item.id, label=item.name) for item in roles],
            departments=[
                AnnouncementTargetOption(id=item.id, label=item.name)
                for item in departments
            ],
            branches=[
                AnnouncementTargetOption(id=item.id, label=item.name) for item in branches
            ],
        )

    async def mark_read(
        self,
        *,
        request_context: RequestContext,
        announcement_id: UUID,
        expected_version: int,
    ) -> AnnouncementDetailRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._require_feature(tenant_id)
        announcement, recipient = await self._locked_recipient(
            tenant_id, actor_id, announcement_id
        )
        if recipient.read_at is None:
            if recipient.version != expected_version:
                raise Phase7VersionConflictError
            recipient.read_at = datetime.now(UTC)
            await self.session.flush()
        return await self._detail(announcement, recipient=recipient, include_targets=False)

    async def acknowledge(
        self,
        *,
        request_context: RequestContext,
        announcement_id: UUID,
        expected_version: int,
    ) -> AnnouncementDetailRead:
        tenant_id, actor_id = _tenant_actor(request_context)
        await self._require_feature(tenant_id)
        announcement, recipient = await self._locked_recipient(
            tenant_id, actor_id, announcement_id
        )
        if not announcement.is_critical:
            raise Phase7ConflictError
        if recipient.acknowledged_at is None:
            if recipient.version != expected_version:
                raise Phase7VersionConflictError
            now = datetime.now(UTC)
            recipient.read_at = recipient.read_at or now
            recipient.acknowledged_at = now
            await self.session.flush()
            await self._audit(
                request_context,
                announcement=announcement,
                event_type=AuditEventType.ANNOUNCEMENT_ACKNOWLEDGED,
                action="acknowledge",
                before_status=announcement.status,
                metadata={"after_status": announcement.status, "version": recipient.version},
                changed_fields=("acknowledged_at", "version"),
            )
        return await self._detail(announcement, recipient=recipient, include_targets=False)

    async def _locked_recipient(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        announcement_id: UUID,
    ) -> tuple[Announcement, AnnouncementRecipient]:
        row = (
            await self.session.execute(
                select(Announcement, AnnouncementRecipient)
                .join(
                    AnnouncementRecipient,
                    and_(
                        AnnouncementRecipient.tenant_id == Announcement.tenant_id,
                        AnnouncementRecipient.announcement_id == Announcement.id,
                    ),
                )
                .where(
                    Announcement.tenant_id == tenant_id,
                    Announcement.id == announcement_id,
                    Announcement.status == AnnouncementStatus.PUBLISHED.value,
                    AnnouncementRecipient.recipient_user_id == actor_id,
                )
                .with_for_update(of=AnnouncementRecipient)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise Phase7NotFoundError
        return row

    async def _locked_draft(
        self, tenant_id: UUID, announcement_id: UUID, expected_version: int
    ) -> Announcement:
        announcement = await self.session.scalar(
            select(Announcement)
            .where(Announcement.tenant_id == tenant_id, Announcement.id == announcement_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if announcement is None:
            raise Phase7NotFoundError
        if announcement.version != expected_version:
            raise Phase7VersionConflictError
        if announcement.status != AnnouncementStatus.DRAFT.value:
            raise Phase7ConflictError
        return announcement

    async def _validate_targets(self, tenant_id: UUID, targets: AnnouncementTargets) -> None:
        if targets.role_ids:
            role_ids = set(
                await self.session.scalars(
                    select(Role.id)
                    .join(RolePermission, RolePermission.role_id == Role.id)
                    .join(Permission, Permission.id == RolePermission.permission_id)
                    .where(
                        Role.id.in_(targets.role_ids),
                        Role.scope_type == "tenant",
                        Permission.code == "announcement:read:own",
                    )
                )
            )
            if role_ids != set(targets.role_ids):
                raise Phase7ValidationError("An announcement role target is unavailable")
        if targets.department_ids:
            department_ids = set(
                await self.session.scalars(
                    select(Department.id).where(
                        Department.tenant_id == tenant_id,
                        Department.id.in_(targets.department_ids),
                        Department.status == "active",
                    )
                )
            )
            if department_ids != set(targets.department_ids):
                raise Phase7ValidationError("An announcement department target is unavailable")
        if targets.branch_ids:
            branch_ids = set(
                await self.session.scalars(
                    select(Branch.id).where(
                        Branch.tenant_id == tenant_id,
                        Branch.id.in_(targets.branch_ids),
                        Branch.status == "active",
                    )
                )
            )
            if branch_ids != set(targets.branch_ids):
                raise Phase7ValidationError("An announcement branch target is unavailable")

    async def _replace_targets(
        self, announcement: Announcement, targets: AnnouncementTargets
    ) -> None:
        filters = {
            "tenant_id": announcement.tenant_id,
            "announcement_id": announcement.id,
        }
        for model in (
            AnnouncementRoleTarget,
            AnnouncementDepartmentTarget,
            AnnouncementBranchTarget,
        ):
            await self.session.execute(delete(model).filter_by(**filters))
        self.session.add_all(
            [
                AnnouncementRoleTarget(
                    tenant_id=announcement.tenant_id,
                    announcement_id=announcement.id,
                    role_id=target_id,
                )
                for target_id in targets.role_ids
            ]
            + [
                AnnouncementDepartmentTarget(
                    tenant_id=announcement.tenant_id,
                    announcement_id=announcement.id,
                    department_id=target_id,
                )
                for target_id in targets.department_ids
            ]
            + [
                AnnouncementBranchTarget(
                    tenant_id=announcement.tenant_id,
                    announcement_id=announcement.id,
                    branch_id=target_id,
                )
                for target_id in targets.branch_ids
            ]
        )

    async def _target_ids(self, tenant_id: UUID, announcement_id: UUID) -> AnnouncementTargets:
        role_ids = list(
            await self.session.scalars(
                select(AnnouncementRoleTarget.role_id).where(
                    AnnouncementRoleTarget.tenant_id == tenant_id,
                    AnnouncementRoleTarget.announcement_id == announcement_id,
                )
            )
        )
        department_ids = list(
            await self.session.scalars(
                select(AnnouncementDepartmentTarget.department_id).where(
                    AnnouncementDepartmentTarget.tenant_id == tenant_id,
                    AnnouncementDepartmentTarget.announcement_id == announcement_id,
                )
            )
        )
        branch_ids = list(
            await self.session.scalars(
                select(AnnouncementBranchTarget.branch_id).where(
                    AnnouncementBranchTarget.tenant_id == tenant_id,
                    AnnouncementBranchTarget.announcement_id == announcement_id,
                )
            )
        )
        return AnnouncementTargets(
            role_ids=role_ids,
            department_ids=department_ids,
            branch_ids=branch_ids,
        )

    async def _recipient_ids(
        self, tenant_id: UUID, targets: AnnouncementTargets
    ) -> list[UUID]:
        today = date.today()
        statement = (
            select(User.id)
            .join(
                TenantMembership,
                and_(
                    TenantMembership.tenant_id == User.tenant_id,
                    TenantMembership.legacy_user_id == User.id,
                ),
            )
            .where(
                User.tenant_id == tenant_id,
                User.status == "active",
                TenantMembership.status == "active",
                exists(
                    select(UserRole.user_id)
                    .join(RolePermission, RolePermission.role_id == UserRole.role_id)
                    .join(
                        Permission,
                        Permission.id == RolePermission.permission_id,
                    )
                    .where(
                        UserRole.tenant_id == tenant_id,
                        UserRole.user_id == User.id,
                        UserRole.active.is_(True),
                        Permission.code == "announcement:read:own",
                    )
                ),
            )
        )
        if targets.role_ids:
            statement = statement.where(
                exists(
                    select(UserRole.user_id).where(
                        UserRole.tenant_id == tenant_id,
                        UserRole.user_id == User.id,
                        UserRole.active.is_(True),
                        UserRole.role_id.in_(targets.role_ids),
                    )
                )
            )
        employee_assignment = (
            select(EmployeeAssignment.id)
            .select_from(EmployeeAccountLink)
            .join(
                EmployeeAssignment,
                and_(
                    EmployeeAssignment.tenant_id == EmployeeAccountLink.tenant_id,
                    EmployeeAssignment.employee_id == EmployeeAccountLink.employee_id,
                ),
            )
            .where(
                EmployeeAccountLink.tenant_id == tenant_id,
                EmployeeAccountLink.membership_id == TenantMembership.id,
                EmployeeAssignment.effective_from <= today,
                or_(
                    EmployeeAssignment.effective_to.is_(None),
                    EmployeeAssignment.effective_to > today,
                ),
            )
        )
        if targets.department_ids:
            statement = statement.where(
                exists(
                    employee_assignment.where(
                        EmployeeAssignment.department_id.in_(targets.department_ids)
                    )
                )
            )
        if targets.branch_ids:
            statement = statement.where(
                exists(
                    employee_assignment.where(
                        EmployeeAssignment.branch_id.in_(targets.branch_ids)
                    )
                )
            )
        return list(
            await self.session.scalars(
                statement.order_by(User.id).limit(ANNOUNCEMENT_RECIPIENT_LIMIT + 1)
            )
        )

    async def _detail(
        self,
        announcement: Announcement,
        *,
        recipient: AnnouncementRecipient | None,
        include_targets: bool,
    ) -> AnnouncementDetailRead:
        return AnnouncementDetailRead(
            **self._summary(announcement, recipient).model_dump(),
            body=announcement.body,
            targets=(
                await self._target_ids(announcement.tenant_id, announcement.id)
                if include_targets
                else None
            ),
        )

    @staticmethod
    def _summary(
        announcement: Announcement, recipient: AnnouncementRecipient | None
    ) -> AnnouncementSummaryRead:
        return AnnouncementSummaryRead(
            id=announcement.id,
            title=announcement.title,
            is_critical=announcement.is_critical,
            status=announcement.status,
            version=recipient.version if recipient is not None else announcement.version,
            published_at=(
                _aware(announcement.published_at)
                if announcement.published_at is not None
                else None
            ),
            archived_at=(
                _aware(announcement.archived_at)
                if announcement.archived_at is not None
                else None
            ),
            read_at=(
                _aware(recipient.read_at)
                if recipient is not None and recipient.read_at is not None
                else None
            ),
            acknowledged_at=(
                _aware(recipient.acknowledged_at)
                if recipient is not None and recipient.acknowledged_at is not None
                else None
            ),
            created_at=_aware(announcement.created_at),
            updated_at=_aware(announcement.updated_at),
        )

    async def _audit(
        self,
        request_context: RequestContext,
        *,
        announcement: Announcement,
        event_type: AuditEventType,
        action: str,
        before_status: str | None,
        metadata: dict[str, object],
        changed_fields: tuple[str, ...],
    ) -> None:
        del before_status
        await self.audit.record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=announcement.tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=request_context.actor_id,
                session_id=request_context.session_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type="announcement",
                resource_id=announcement.id,
                action=action,
                result=AuditResult.SUCCESS,
                changed_fields=changed_fields,
                metadata=metadata,
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
                context=AuditContext.from_request_context(request_context),
            )
        )

    async def _require_feature(self, tenant_id: UUID) -> None:
        await require_phase7_feature(
            self.session, tenant_id=tenant_id, feature=FeatureFlagKey.SELF_SERVICE
        )


def _decode_cursor(
    token: str | None,
    *,
    manage: bool,
    status: AnnouncementStatus | None,
) -> tuple[datetime, UUID] | None:
    if token is None:
        return None
    try:
        values = decode_cursor(token, expected_resource=_CURSOR_RESOURCE)
        if set(values) != {"created_at", "id", "manage", "status"}:
            raise InvalidCursorError
        if values["manage"] != ("1" if manage else "0"):
            raise InvalidCursorError
        if values["status"] != (status.value if status is not None else ""):
            raise InvalidCursorError
        created_at = datetime.fromisoformat(values["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise InvalidCursorError
        return created_at, UUID(values["id"])
    except (InvalidCursorError, ValueError) as exc:
        raise Phase7ValidationError("The announcement cursor is invalid") from exc


def _tenant_actor(context: RequestContext) -> tuple[UUID, UUID]:
    if context.actor_id is None:
        raise RuntimeError("Announcement context requires an actor")
    return context.require_tenant().tenant_id, context.actor_id


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["ANNOUNCEMENT_RECIPIENT_LIMIT", "AnnouncementService"]
