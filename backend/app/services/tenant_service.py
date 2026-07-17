from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave import HolidayCalendar, LeavePolicy, LeaveType
from app.models.organization import LegalEntity, LegalEntityStatus
from app.models.privacy import PrivacyConsentPurpose
from app.models.tenant import Tenant, TenantFeatureFlag, TenantSettings
from app.modules.core.domain.feature_flags import FEATURE_FLAG_DEFAULTS
from app.modules.core.domain.tenant import (
    TenantAccessMode,
    TenantDateFormat,
    TenantStatus,
    TenantTimeFormat,
    TenantWeekStartDay,
    access_mode_for_status,
    transition_tenant_status,
)
from app.platform.db import constraint_name_from_error
from app.platform.errors.application import ApplicationError
from app.platform.pagination import CursorPage
from app.schemas.tenant import (
    TenantListCursor,
    TenantListPagination,
    TenantPlatformCreate,
    TenantPlatformUpdate,
    TenantSettingsUpdate,
)

TENANT_SLUG_UNIQUE_CONSTRAINTS = frozenset({"tenants_slug_key", "uq_tenants_slug"})
_SQLITE_TENANT_SLUG_UNIQUE_SIGNATURE = "UNIQUE constraint failed: tenants.slug"
_LEAVE_POLICY_EFFECTIVE_FROM = date(1900, 1, 1)
_STARTER_LEAVE_TYPES = (
    ("annual", "Annual leave", True, False),
    ("excuse", "Excuse leave", True, False),
    ("unpaid", "Unpaid leave", False, False),
    ("medical_report", "Medical/report leave", True, True),
)


class TenantNotFoundError(ApplicationError):
    pass


class DuplicateTenantSlugError(ApplicationError):
    pass


class TenantLifecycleConflictError(ApplicationError):
    pass


class TenantNotReadyError(ApplicationError):
    pass


class TenantClosedError(ApplicationError):
    pass


class TenantReadOnlyError(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class TenantSettingsSnapshot:
    locale: str
    timezone: str
    week_start_day: str
    date_format: str
    time_format: str


@dataclass(frozen=True, slots=True)
class TenantUpdateMutation:
    tenant: Tenant
    previous_status: TenantStatus
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TenantSettingsMutation:
    settings: TenantSettingsSnapshot
    changed_fields: tuple[str, ...]


class TenantService:
    """Focused tenant metadata, lifecycle, and typed-settings persistence service."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tenant_page(
        self,
        pagination: TenantListPagination | None = None,
    ) -> CursorPage[Tenant]:
        pagination = pagination or TenantListPagination()
        statement = _tenant_list_statement(
            pagination,
            dialect_name=self.session.get_bind().dialect.name,
        )
        rows = list(await self.session.scalars(statement))
        items = rows[: pagination.limit]
        next_cursor = None
        if len(rows) > pagination.limit:
            last_item = items[-1]
            created_at = last_item.created_at
            if not isinstance(created_at, datetime):  # pragma: no cover - ORM contract guard
                raise RuntimeError("Tenant created_at must be a datetime")
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            next_cursor = TenantListCursor(created_at=created_at, id=last_item.id).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise TenantNotFoundError
        return tenant

    async def create_tenant(self, payload: TenantPlatformCreate) -> Tenant:
        await self._ensure_tenant_slug_available(payload.slug)

        tenant = Tenant(
            id=uuid4(),
            slug=payload.slug,
            name=payload.name,
            status=TenantStatus.PROVISIONING.value,
            plan_code=payload.plan_code.value,
            data_region=payload.data_region.value,
            locale=payload.locale.value,
            timezone=payload.timezone,
            active_employee_limit=payload.limits.active_employees,
        )
        self.session.add(tenant)
        await self._flush_tenant_write()

        self.session.add(
            TenantSettings(
                tenant_id=tenant.id,
                week_start_day=payload.settings.week_start_day.value,
                date_format=payload.settings.date_format.value,
                time_format=payload.settings.time_format.value,
            )
        )
        self.session.add(
            PrivacyConsentPurpose(
                id=uuid4(),
                tenant_id=tenant.id,
                code="optional_communications",
                version=1,
                title="İsteğe bağlı iletişimler",
                description=(
                    "Zorunlu olmayan çalışan iletişimleri için isteğe bağlı onay."
                ),
                is_active=True,
                created_at=datetime.now(UTC),
            )
        )
        self.session.add(
            LegalEntity(
                id=tenant.id,
                tenant_id=tenant.id,
                code="DEFAULT",
                name=tenant.name,
                registered_name=tenant.name,
                country_code=None,
                tax_number=None,
                timezone=tenant.timezone,
                status=LegalEntityStatus.ACTIVE.value,
                is_default=True,
            )
        )
        self.session.add_all(
            TenantFeatureFlag(
                tenant_id=tenant.id,
                key=key.value,
                enabled=enabled,
            )
            for key, enabled in FEATURE_FLAG_DEFAULTS.items()
        )
        leave_configuration = _starter_leave_configuration(tenant.id)
        self.session.add_all(
            item for item in leave_configuration if not isinstance(item, LeavePolicy)
        )
        await self.session.flush()
        self.session.add_all(item for item in leave_configuration if isinstance(item, LeavePolicy))
        await self.session.flush()
        await self.session.refresh(tenant)
        return tenant

    async def update_tenant(
        self,
        tenant_id: UUID,
        payload: TenantPlatformUpdate,
    ) -> Tenant:
        return (await self.update_tenant_with_changes(tenant_id, payload)).tenant

    async def update_tenant_with_changes(
        self,
        tenant_id: UUID,
        payload: TenantPlatformUpdate,
    ) -> TenantUpdateMutation:
        tenant = await self._get_tenant_for_update(tenant_id)
        values = _provided_tenant_values(payload)
        current_status = TenantStatus(tenant.status)
        next_status = values.get("status", current_status)
        if not isinstance(next_status, TenantStatus):
            next_status = TenantStatus(next_status)

        try:
            transition_tenant_status(current_status, next_status)
        except ValueError as exc:
            raise TenantLifecycleConflictError(str(exc)) from exc

        changed_fields = {
            field_name
            for field_name, value in values.items()
            if _enum_value(value) != getattr(tenant, field_name)
        }
        non_status_changed_fields = changed_fields - {"status"}
        if current_status is TenantStatus.CLOSED and non_status_changed_fields:
            raise TenantLifecycleConflictError("Closed tenants are immutable")
        if current_status is TenantStatus.OFFBOARDING and non_status_changed_fields:
            raise TenantLifecycleConflictError(
                "Offboarding tenants can only transition to closed"
            )
        if (
            next_status in {TenantStatus.OFFBOARDING, TenantStatus.CLOSED}
            and next_status is not current_status
            and non_status_changed_fields
        ):
            raise TenantLifecycleConflictError(
                "Offboarding or closure must be requested separately from metadata changes"
            )
        if (
            "data_region" in non_status_changed_fields
            and (
                current_status is not TenantStatus.PROVISIONING
                or next_status is not TenantStatus.PROVISIONING
            )
        ):
            raise TenantLifecycleConflictError(
                "Tenant data region can only change while the tenant remains provisioning"
            )

        for field_name, value in values.items():
            setattr(tenant, field_name, _enum_value(value))
        await self._flush_tenant_write()
        await self.session.refresh(tenant)
        return TenantUpdateMutation(
            tenant=tenant,
            previous_status=current_status,
            changed_fields=tuple(sorted(changed_fields)),
        )

    async def get_current_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = await self.get_tenant(tenant_id)
        _ensure_tenant_read_access(TenantStatus(tenant.status))
        return tenant

    async def get_tenant_settings(self, tenant_id: UUID) -> TenantSettingsSnapshot:
        tenant = await self.get_tenant(tenant_id)
        _ensure_tenant_read_access(TenantStatus(tenant.status))
        settings = await self.session.get(TenantSettings, tenant_id)
        return _settings_snapshot(tenant, settings)

    async def update_tenant_settings(
        self,
        tenant_id: UUID,
        payload: TenantSettingsUpdate,
    ) -> TenantSettingsSnapshot:
        return (
            await self.update_tenant_settings_with_changes(tenant_id, payload)
        ).settings

    async def update_tenant_settings_with_changes(
        self,
        tenant_id: UUID,
        payload: TenantSettingsUpdate,
    ) -> TenantSettingsMutation:
        tenant = await self._get_tenant_for_update(tenant_id)
        _ensure_tenant_write_access(TenantStatus(tenant.status))
        settings = await self.session.scalar(
            select(TenantSettings)
            .where(TenantSettings.tenant_id == tenant_id)
            .with_for_update()
        )
        if settings is None:
            settings = TenantSettings(
                tenant_id=tenant_id,
                week_start_day=TenantWeekStartDay.MONDAY.value,
                date_format=TenantDateFormat.DAY_MONTH_YEAR.value,
                time_format=TenantTimeFormat.HOUR_24.value,
            )
            self.session.add(settings)

        values = _provided_values(payload)
        changed_fields: list[str] = []
        for field_name, value in values.items():
            target = tenant if field_name in {"locale", "timezone"} else settings
            normalized_value = _enum_value(value)
            if normalized_value != getattr(target, field_name):
                changed_fields.append(field_name)
                setattr(target, field_name, normalized_value)

        await self.session.flush()
        await self.session.refresh(tenant)
        await self.session.refresh(settings)
        return TenantSettingsMutation(
            settings=_settings_snapshot(tenant, settings),
            changed_fields=tuple(sorted(changed_fields)),
        )

    async def _get_tenant_for_update(self, tenant_id: UUID) -> Tenant:
        tenant = await self.session.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None:
            raise TenantNotFoundError
        return tenant

    async def _ensure_tenant_slug_available(self, slug: str) -> None:
        if await self.session.scalar(select(Tenant.id).where(Tenant.slug == slug)):
            raise DuplicateTenantSlugError

    async def _flush_tenant_write(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if _is_tenant_slug_unique_violation(exc):
                raise DuplicateTenantSlugError from exc
            raise


def _provided_values(
    payload: TenantPlatformUpdate | TenantSettingsUpdate,
) -> dict[str, object]:
    return {
        field_name: getattr(payload, field_name)
        for field_name in payload.model_fields_set
    }


def _starter_leave_configuration(
    tenant_id: UUID,
) -> tuple[LeaveType | HolidayCalendar | LeavePolicy, ...]:
    configuration: list[LeaveType | HolidayCalendar | LeavePolicy] = []
    created_at = datetime.now(UTC)
    for code, name, paid, document_required in _STARTER_LEAVE_TYPES:
        leave_type_id = _deterministic_uuid(f"p6:leave-type:{tenant_id}:{code}")
        configuration.append(
            LeaveType(
                id=leave_type_id,
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=None,
                is_active=True,
                version=1,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        configuration.append(
            LeavePolicy(
                id=_deterministic_uuid(f"p6:leave-policy:{tenant_id}:{leave_type_id}:1"),
                tenant_id=tenant_id,
                leave_type_id=leave_type_id,
                version=1,
                effective_from=_LEAVE_POLICY_EFFECTIVE_FROM,
                paid=paid,
                document_required=document_required,
                negative_balance_allowed=False,
                accrual_enabled=False,
                accrual_days_per_month=Decimal("0.00"),
                carryover_enabled=False,
                carryover_limit_days=None,
                created_by_user_id=None,
                created_at=created_at,
            )
        )
    configuration.append(
        HolidayCalendar(
            id=_deterministic_uuid(f"p6:holiday-calendar:{tenant_id}:default"),
            tenant_id=tenant_id,
            name="Default work calendar",
            is_default=True,
            is_active=True,
            non_working_weekdays=[5, 6],
            version=1,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    return tuple(configuration)


def _deterministic_uuid(value: str) -> UUID:
    digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
    return UUID(digest, version=4)


def _provided_tenant_values(payload: TenantPlatformUpdate) -> dict[str, object]:
    values = _provided_values(payload)
    limits = values.pop("limits", None)
    if limits is not None:
        values["active_employee_limit"] = limits.active_employees
    return values


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _ensure_tenant_read_access(status: TenantStatus) -> None:
    access_mode = access_mode_for_status(status)
    if access_mode is TenantAccessMode.PLATFORM_ONLY:
        raise TenantNotReadyError
    if access_mode is TenantAccessMode.DENIED:
        raise TenantClosedError


def _ensure_tenant_write_access(status: TenantStatus) -> None:
    access_mode = access_mode_for_status(status)
    if access_mode is TenantAccessMode.PLATFORM_ONLY:
        raise TenantNotReadyError
    if access_mode is TenantAccessMode.DENIED:
        raise TenantClosedError
    if access_mode is TenantAccessMode.READ_ONLY:
        raise TenantReadOnlyError


def _settings_snapshot(
    tenant: Tenant,
    settings: TenantSettings | None,
) -> TenantSettingsSnapshot:
    return TenantSettingsSnapshot(
        locale=tenant.locale,
        timezone=tenant.timezone,
        week_start_day=(
            settings.week_start_day
            if settings is not None
            else TenantWeekStartDay.MONDAY.value
        ),
        date_format=(
            settings.date_format
            if settings is not None
            else TenantDateFormat.DAY_MONTH_YEAR.value
        ),
        time_format=(
            settings.time_format
            if settings is not None
            else TenantTimeFormat.HOUR_24.value
        ),
    )


def _is_tenant_slug_unique_violation(exc: IntegrityError) -> bool:
    if constraint_name_from_error(exc) in TENANT_SLUG_UNIQUE_CONSTRAINTS:
        return True
    return _SQLITE_TENANT_SLUG_UNIQUE_SIGNATURE in str(exc.orig)


def _tenant_list_statement(
    pagination: TenantListPagination,
    *,
    dialect_name: str,
):
    is_sqlite = dialect_name == "sqlite"
    created_at_key = func.julianday(Tenant.created_at) if is_sqlite else Tenant.created_at
    statement = select(Tenant)
    if pagination.cursor is not None:
        cursor_created_at_key = (
            func.julianday(pagination.cursor.created_at)
            if is_sqlite
            else pagination.cursor.created_at
        )
        statement = statement.where(
            or_(
                created_at_key > cursor_created_at_key,
                and_(
                    created_at_key == cursor_created_at_key,
                    Tenant.id > pagination.cursor.id,
                ),
            )
        )
    return statement.order_by(created_at_key.asc(), Tenant.id.asc()).limit(
        pagination.limit + 1
    )
