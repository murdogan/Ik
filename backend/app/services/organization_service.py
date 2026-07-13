"""Authenticated tenant organization reads and audited commands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import (
    Branch,
    BranchStatus,
    LegalEntity,
    LegalEntityStatus,
)
from app.models.tenant import Tenant, TenantFeatureFlag
from app.modules.core.domain.feature_flags import (
    FeatureFlagKey,
    default_feature_flag_enabled,
)
from app.modules.core.domain.tenant import (
    TenantAccessMode,
    TenantStatus,
    access_mode_for_status,
)
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
from app.platform.authorization import DenyByDefaultPolicy
from app.platform.db import (
    SqlAlchemyUnitOfWork,
    configure_tenant_database_access,
    constraint_name_from_error,
)
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.platform.request_context import RequestContext
from app.schemas.organization import (
    BranchCreate,
    BranchListPagination,
    BranchUpdate,
    LegalEntityCreate,
    LegalEntityListCursor,
    LegalEntityListPagination,
    LegalEntityUpdate,
)
from app.services.audit_recorder import SqlAlchemyAuditRecorder
from app.services.tenant_service import (
    TenantClosedError,
    TenantNotFoundError,
    TenantNotReadyError,
    TenantReadOnlyError,
)

LEGAL_ENTITY_CODE_UNIQUE_CONSTRAINT = "uq_legal_entities_tenant_code_normalized"
BRANCH_CODE_UNIQUE_CONSTRAINT = "uq_branches_tenant_code_normalized"
ORGANIZATION_READ_PERMISSION = "organization:read:tenant"
ORGANIZATION_UPDATE_PERMISSION = "organization:update:tenant"

_authorization_policy = DenyByDefaultPolicy()


class OrganizationAccessDeniedError(ApplicationError):
    pass


class LegalEntityNotFoundError(ApplicationError):
    pass


class BranchNotFoundError(ApplicationError):
    pass


class DuplicateLegalEntityCodeError(ApplicationError):
    pass


class DuplicateBranchCodeError(ApplicationError):
    pass


class OrganizationConflictError(ApplicationError):
    pass


class OrganizationFeatureUnavailableError(ApplicationError):
    pass


class BranchNotAssignableError(OrganizationConflictError):
    pass


class OrganizationService:
    """Bounded organization queries and same-transaction audited mutations."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        audit_recorder_factory: Callable[[AsyncSession], AuditRecorder] = (
            SqlAlchemyAuditRecorder
        ),
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder_factory = audit_recorder_factory

    async def list_legal_entities(
        self,
        *,
        request_context: RequestContext,
        pagination: LegalEntityListPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[LegalEntity]:
        tenant_id, _actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_READ_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _require_tenant_access(session, tenant_id, write=False)
                statement = select(LegalEntity).where(LegalEntity.tenant_id == tenant_id)
                if pagination.cursor is not None:
                    statement = statement.where(
                        or_(
                            LegalEntity.code_normalized > pagination.cursor.code,
                            and_(
                                LegalEntity.code_normalized == pagination.cursor.code,
                                LegalEntity.id > pagination.cursor.id,
                            ),
                        )
                    )
                rows = list(
                    await session.scalars(
                        statement.order_by(
                            LegalEntity.code_normalized.asc(),
                            LegalEntity.id.asc(),
                        ).limit(pagination.limit + 1)
                    )
                )
        items = rows[: pagination.limit]
        next_cursor = None
        if len(rows) > pagination.limit:
            last_item = items[-1]
            next_cursor = LegalEntityListCursor(
                code=last_item.code_normalized,
                id=last_item.id,
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_legal_entity(
        self,
        *,
        request_context: RequestContext,
        legal_entity_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> LegalEntity:
        tenant_id, _actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_READ_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _require_tenant_access(session, tenant_id, write=False)
                legal_entity = await _legal_entity(
                    session,
                    tenant_id=tenant_id,
                    legal_entity_id=legal_entity_id,
                )
        if legal_entity is None:
            raise LegalEntityNotFoundError()
        return legal_entity

    async def create_legal_entity(
        self,
        *,
        request_context: RequestContext,
        payload: LegalEntityCreate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> LegalEntity:
        tenant_id, actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_UPDATE_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> LegalEntity:
                await _require_tenant_access(session, tenant_id, write=True)
                await _require_legal_entity_code_available(
                    session,
                    tenant_id=tenant_id,
                    code=payload.code,
                )
                legal_entity = LegalEntity(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    code=payload.code,
                    name=payload.name,
                    registered_name=payload.registered_name,
                    country_code=payload.country_code,
                    tax_number=payload.tax_number,
                    timezone=payload.timezone,
                    status=LegalEntityStatus.ACTIVE.value,
                    is_default=False,
                )
                session.add(legal_entity)
                await _flush_organization_write(session, resource="legal_entity")
                await session.refresh(legal_entity)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.LEGAL_ENTITY_CREATED,
                    resource_type="legal_entity",
                    resource_id=legal_entity.id,
                    action="create",
                    changed_fields=(
                        "code",
                        "name",
                        "registered_name",
                        "country_code",
                        "tax_number",
                        "timezone",
                        "status",
                    ),
                )
                return legal_entity

            return await unit_of_work.execute(operation)

    async def update_legal_entity(
        self,
        *,
        request_context: RequestContext,
        legal_entity_id: UUID,
        payload: LegalEntityUpdate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> LegalEntity:
        tenant_id, actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_UPDATE_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> LegalEntity:
                await _require_tenant_access(session, tenant_id, write=True)
                legal_entity = await _legal_entity(
                    session,
                    tenant_id=tenant_id,
                    legal_entity_id=legal_entity_id,
                    for_update=True,
                )
                if legal_entity is None:
                    raise LegalEntityNotFoundError()
                values = _provided_values(payload)
                requested_status = values.get("status")
                if requested_status is not None:
                    requested_status = _enum_value(requested_status)
                    if legal_entity.is_default and requested_status != LegalEntityStatus.ACTIVE:
                        raise OrganizationConflictError(
                            "The default legal entity must remain active"
                        )
                    if (
                        requested_status == LegalEntityStatus.INACTIVE.value
                        and legal_entity.status != LegalEntityStatus.INACTIVE.value
                        and await _has_active_branches(
                            session,
                            tenant_id=tenant_id,
                            legal_entity_id=legal_entity.id,
                        )
                    ):
                        raise OrganizationConflictError(
                            "A legal entity with active branches cannot be made inactive"
                        )

                changed_fields: list[str] = []
                for field_name, value in values.items():
                    normalized = _enum_value(value)
                    if normalized != getattr(legal_entity, field_name):
                        setattr(legal_entity, field_name, normalized)
                        changed_fields.append(field_name)
                if changed_fields:
                    legal_entity.updated_at = datetime.now(UTC)
                    await _flush_organization_write(session, resource="legal_entity")
                    await session.refresh(legal_entity)
                    await self._record_event(
                        session,
                        request_context=request_context,
                        audit_context=audit_context,
                        actor_id=actor_id,
                        event_type=AuditEventType.LEGAL_ENTITY_UPDATED,
                        resource_type="legal_entity",
                        resource_id=legal_entity.id,
                        action="update",
                        changed_fields=tuple(sorted(changed_fields)),
                    )
                return legal_entity

            return await unit_of_work.execute(operation)

    async def list_branches(
        self,
        *,
        request_context: RequestContext,
        pagination: BranchListPagination,
        granted_permissions: tuple[str, ...],
    ) -> CursorPage[Branch]:
        tenant_id, _actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_READ_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _require_tenant_access(session, tenant_id, write=False)
                statement = select(Branch).where(Branch.tenant_id == tenant_id)
                if pagination.status is not None:
                    statement = statement.where(Branch.status == pagination.status.value)
                if pagination.legal_entity_id is not None:
                    statement = statement.where(
                        Branch.legal_entity_id == pagination.legal_entity_id
                    )
                if pagination.cursor is not None:
                    statement = statement.where(
                        or_(
                            Branch.code_normalized > pagination.cursor.code,
                            and_(
                                Branch.code_normalized == pagination.cursor.code,
                                Branch.id > pagination.cursor.id,
                            ),
                        )
                    )
                rows = list(
                    await session.scalars(
                        statement.order_by(
                            Branch.code_normalized.asc(),
                            Branch.id.asc(),
                        ).limit(pagination.limit + 1)
                    )
                )
        items = rows[: pagination.limit]
        next_cursor = None
        if len(rows) > pagination.limit:
            last_item = items[-1]
            next_cursor = pagination.next_cursor(
                code=last_item.code_normalized,
                branch_id=last_item.id,
            )
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_branch(
        self,
        *,
        request_context: RequestContext,
        branch_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> Branch:
        tenant_id, _actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_READ_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _require_tenant_access(session, tenant_id, write=False)
                branch = await _branch(
                    session,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                )
        if branch is None:
            raise BranchNotFoundError()
        return branch

    async def require_assignable_branch(
        self,
        *,
        request_context: RequestContext,
        branch_id: UUID,
        granted_permissions: tuple[str, ...],
    ) -> Branch:
        """Resolve only an active branch under an active legal entity for new assignments."""

        tenant_id, _actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_READ_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            async with session.begin():
                await _require_tenant_access(session, tenant_id, write=False)
                branch = await session.scalar(
                    select(Branch)
                    .join(
                        LegalEntity,
                        and_(
                            LegalEntity.tenant_id == Branch.tenant_id,
                            LegalEntity.id == Branch.legal_entity_id,
                        ),
                    )
                    .where(
                        Branch.tenant_id == tenant_id,
                        Branch.id == branch_id,
                        Branch.status == BranchStatus.ACTIVE.value,
                        Branch.archived_at.is_(None),
                        LegalEntity.status == LegalEntityStatus.ACTIVE.value,
                    )
                )
                if branch is not None:
                    return branch
                existing_id = await session.scalar(
                    select(Branch.id).where(
                        Branch.tenant_id == tenant_id,
                        Branch.id == branch_id,
                    )
                )
        if existing_id is None:
            raise BranchNotFoundError()
        raise BranchNotAssignableError(
            "Archived or inactive branches cannot accept new assignments"
        )

    async def create_branch(
        self,
        *,
        request_context: RequestContext,
        payload: BranchCreate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> Branch:
        tenant_id, actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_UPDATE_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> Branch:
                await _require_tenant_access(session, tenant_id, write=True)
                legal_entity = await _legal_entity(
                    session,
                    tenant_id=tenant_id,
                    legal_entity_id=payload.legal_entity_id,
                    # Serialize against legal-entity deactivation. Both commands take the
                    # parent lock before inspecting active-child state.
                    for_update=True,
                )
                if legal_entity is None:
                    raise LegalEntityNotFoundError()
                if legal_entity.status != LegalEntityStatus.ACTIVE.value:
                    raise OrganizationConflictError(
                        "Branches can only be created under an active legal entity"
                    )
                await _require_branch_code_available(
                    session,
                    tenant_id=tenant_id,
                    code=payload.code,
                )
                branch = Branch(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    legal_entity_id=payload.legal_entity_id,
                    code=payload.code,
                    name=payload.name,
                    timezone=payload.timezone,
                    country_code=payload.country_code,
                    city=payload.city,
                    address=payload.address,
                    status=BranchStatus.ACTIVE.value,
                    archived_at=None,
                )
                session.add(branch)
                await _flush_organization_write(session, resource="branch")
                await session.refresh(branch)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.BRANCH_CREATED,
                    resource_type="branch",
                    resource_id=branch.id,
                    action="create",
                    changed_fields=(
                        "legal_entity_id",
                        "code",
                        "name",
                        "timezone",
                        "country_code",
                        "city",
                        "address",
                        "status",
                    ),
                )
                return branch

            return await unit_of_work.execute(operation)

    async def update_branch(
        self,
        *,
        request_context: RequestContext,
        branch_id: UUID,
        payload: BranchUpdate,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> Branch:
        tenant_id, actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_UPDATE_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> Branch:
                await _require_tenant_access(session, tenant_id, write=True)
                branch = await _branch(
                    session,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    for_update=True,
                )
                if branch is None:
                    raise BranchNotFoundError()
                if branch.status == BranchStatus.ARCHIVED.value:
                    raise OrganizationConflictError(
                        "Archived branches are historical and cannot be updated"
                    )
                changed_fields: list[str] = []
                for field_name, value in _provided_values(payload).items():
                    if value != getattr(branch, field_name):
                        setattr(branch, field_name, value)
                        changed_fields.append(field_name)
                if changed_fields:
                    branch.updated_at = datetime.now(UTC)
                    await _flush_organization_write(session, resource="branch")
                    await session.refresh(branch)
                    await self._record_event(
                        session,
                        request_context=request_context,
                        audit_context=audit_context,
                        actor_id=actor_id,
                        event_type=AuditEventType.BRANCH_UPDATED,
                        resource_type="branch",
                        resource_id=branch.id,
                        action="update",
                        changed_fields=tuple(sorted(changed_fields)),
                    )
                return branch

            return await unit_of_work.execute(operation)

    async def archive_branch(
        self,
        *,
        request_context: RequestContext,
        branch_id: UUID,
        granted_permissions: tuple[str, ...],
        audit_context: AuditContext | None = None,
    ) -> Branch:
        tenant_id, actor_id = _scope_from_context(request_context)
        _require_permission(granted_permissions, ORGANIZATION_UPDATE_PERMISSION)
        async with self._session_factory() as session:
            configure_tenant_database_access(session, tenant_id)
            unit_of_work = SqlAlchemyUnitOfWork(session)

            async def operation() -> Branch:
                await _require_tenant_access(session, tenant_id, write=True)
                branch = await _branch(
                    session,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    for_update=True,
                )
                if branch is None:
                    raise BranchNotFoundError()
                if branch.status == BranchStatus.ARCHIVED.value:
                    return branch
                branch.status = BranchStatus.ARCHIVED.value
                branch.archived_at = datetime.now(UTC)
                branch.updated_at = branch.archived_at
                await _flush_organization_write(session, resource="branch")
                await session.refresh(branch)
                await self._record_event(
                    session,
                    request_context=request_context,
                    audit_context=audit_context,
                    actor_id=actor_id,
                    event_type=AuditEventType.BRANCH_ARCHIVED,
                    resource_type="branch",
                    resource_id=branch.id,
                    action="archive",
                    changed_fields=("status", "archived_at"),
                    metadata={
                        "before_status": BranchStatus.ACTIVE.value,
                        "after_status": BranchStatus.ARCHIVED.value,
                    },
                )
                return branch

            return await unit_of_work.execute(operation)

    async def _record_event(
        self,
        session: AsyncSession,
        *,
        request_context: RequestContext,
        audit_context: AuditContext | None,
        actor_id: UUID,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: UUID,
        action: str,
        changed_fields: tuple[str, ...],
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self._audit_recorder_factory(session).record(
            AuditEventDraft(
                scope_type=AuditScopeType.TENANT,
                tenant_id=request_context.require_tenant().tenant_id,
                actor_type=AuditActorType.USER,
                actor_user_id=actor_id,
                event_type=event_type,
                category=AuditCategory.HR_OPERATIONS,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                context=audit_context or AuditContext.from_request_context(request_context),
                session_id=request_context.session_id,
                changed_fields=changed_fields,
                metadata=metadata or {},
                data_classification=AuditDataClassification.HR_METADATA,
                visibility_class=AuditVisibilityClass.HR_OPERATIONS,
            )
        )


def _scope_from_context(request_context: RequestContext) -> tuple[UUID, UUID]:
    tenant_id = request_context.require_tenant().tenant_id
    actor_id = request_context.actor_id
    if actor_id is None:
        raise OrganizationAccessDeniedError()
    return tenant_id, actor_id


def _require_permission(granted_permissions: tuple[str, ...], permission: str) -> None:
    if not _authorization_policy.allows(permission, granted_permissions):
        raise OrganizationAccessDeniedError()


async def _require_tenant_access(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    write: bool,
) -> None:
    tenant_statement = select(Tenant).where(Tenant.id == tenant_id)
    if write:
        # Serialize tenant-owned commands with platform lifecycle transitions. A write that waits
        # behind suspension/offboarding must observe the new read-only state before mutating.
        tenant_statement = tenant_statement.with_for_update()
    tenant = await session.scalar(tenant_statement)
    if tenant is None:
        raise TenantNotFoundError()
    access_mode = access_mode_for_status(TenantStatus(tenant.status))
    if access_mode is TenantAccessMode.PLATFORM_ONLY:
        raise TenantNotReadyError()
    if access_mode is TenantAccessMode.DENIED:
        raise TenantClosedError()
    if write and access_mode is TenantAccessMode.READ_ONLY:
        raise TenantReadOnlyError()
    organization_enabled = await session.scalar(
        select(TenantFeatureFlag.enabled).where(
            TenantFeatureFlag.tenant_id == tenant_id,
            TenantFeatureFlag.key == FeatureFlagKey.ORGANIZATION.value,
        )
    )
    if organization_enabled is None:
        organization_enabled = default_feature_flag_enabled(FeatureFlagKey.ORGANIZATION)
    if not organization_enabled:
        raise OrganizationFeatureUnavailableError()


async def _legal_entity(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    legal_entity_id: UUID,
    for_update: bool = False,
) -> LegalEntity | None:
    statement = select(LegalEntity).where(
        LegalEntity.tenant_id == tenant_id,
        LegalEntity.id == legal_entity_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _branch(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    branch_id: UUID,
    for_update: bool = False,
) -> Branch | None:
    statement = select(Branch).where(
        Branch.tenant_id == tenant_id,
        Branch.id == branch_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def _has_active_branches(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    legal_entity_id: UUID,
) -> bool:
    return bool(
        await session.scalar(
            select(func.count())
            .select_from(Branch)
            .where(
                Branch.tenant_id == tenant_id,
                Branch.legal_entity_id == legal_entity_id,
                Branch.status == BranchStatus.ACTIVE.value,
            )
        )
    )


async def _require_legal_entity_code_available(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    code: str,
) -> None:
    if await session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.tenant_id == tenant_id,
            LegalEntity.code_normalized == code.strip().lower(),
        )
    ):
        raise DuplicateLegalEntityCodeError()


async def _require_branch_code_available(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    code: str,
) -> None:
    if await session.scalar(
        select(Branch.id).where(
            Branch.tenant_id == tenant_id,
            Branch.code_normalized == code.strip().lower(),
        )
    ):
        raise DuplicateBranchCodeError()


async def _flush_organization_write(
    session: AsyncSession,
    *,
    resource: str,
) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        constraint_name = constraint_name_from_error(exc)
        error_text = str(exc.orig)
        if (
            constraint_name == LEGAL_ENTITY_CODE_UNIQUE_CONSTRAINT
            or "legal_entities.tenant_id, legal_entities.code_normalized" in error_text
        ):
            raise DuplicateLegalEntityCodeError() from exc
        if (
            constraint_name == BRANCH_CODE_UNIQUE_CONSTRAINT
            or "branches.tenant_id, branches.code_normalized" in error_text
        ):
            raise DuplicateBranchCodeError() from exc
        if resource == "branch" and "legal_entities" in error_text:
            raise LegalEntityNotFoundError() from exc
        raise


def _provided_values(payload: LegalEntityUpdate | BranchUpdate) -> dict[str, object]:
    return {
        field_name: getattr(payload, field_name)
        for field_name in payload.model_fields_set
    }


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


__all__ = [
    "BRANCH_CODE_UNIQUE_CONSTRAINT",
    "LEGAL_ENTITY_CODE_UNIQUE_CONSTRAINT",
    "ORGANIZATION_READ_PERMISSION",
    "ORGANIZATION_UPDATE_PERMISSION",
    "BranchNotAssignableError",
    "BranchNotFoundError",
    "DuplicateBranchCodeError",
    "DuplicateLegalEntityCodeError",
    "LegalEntityNotFoundError",
    "OrganizationAccessDeniedError",
    "OrganizationConflictError",
    "OrganizationFeatureUnavailableError",
    "OrganizationService",
]
