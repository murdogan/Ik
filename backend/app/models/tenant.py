from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.core.domain import (
    TenantAccessMode,
    TenantDateFormat,
    TenantHealth,
    TenantLocale,
    TenantPlan,
    TenantRegion,
    TenantStatus,
    TenantTimeFormat,
    TenantWeekStartDay,
)

__all__ = [
    "Tenant",
    "TenantAccessMode",
    "TenantDateFormat",
    "TenantHealth",
    "TenantLocale",
    "TenantPlan",
    "TenantRegion",
    "TenantSettings",
    "TenantStatus",
    "TenantTimeFormat",
    "TenantWeekStartDay",
]


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status in ('provisioning','trial','active','suspended','offboarding','closed')",
            name="ck_tenants_status",
        ),
        UniqueConstraint("slug"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TenantStatus.PROVISIONING.value
    )
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, default="core")
    data_region: Mapped[str] = mapped_column(String(32), nullable=False, default="tr-1")
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="tr-TR")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Istanbul")


class TenantSettings(Base, TimestampMixin):
    __tablename__ = "tenant_settings"
    __table_args__ = (
        CheckConstraint(
            "week_start_day in ('monday','sunday')",
            name="ck_tenant_settings_week_start_day",
        ),
        CheckConstraint(
            "date_format in ('DD.MM.YYYY','MM/DD/YYYY','YYYY-MM-DD')",
            name="ck_tenant_settings_date_format",
        ),
        CheckConstraint(
            "time_format in ('24h','12h')",
            name="ck_tenant_settings_time_format",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "tenants.id",
            name="fk_tenant_settings_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    week_start_day: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TenantWeekStartDay.MONDAY.value,
        server_default=TenantWeekStartDay.MONDAY.value,
    )
    date_format: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TenantDateFormat.DAY_MONTH_YEAR.value,
        server_default=TenantDateFormat.DAY_MONTH_YEAR.value,
    )
    time_format: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=TenantTimeFormat.HOUR_24.value,
        server_default=TenantTimeFormat.HOUR_24.value,
    )
