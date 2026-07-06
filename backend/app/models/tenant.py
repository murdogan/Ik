from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TenantStatus(StrEnum):
    PROVISIONING = "provisioning"
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDING = "offboarding"
    CLOSED = "closed"


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
