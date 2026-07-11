"""Narrow platform-only tenant metadata queries.

The projections in this module intentionally name every selected column. Platform operational
reads must never grow by joining HR tables or by deriving usage counters from customer records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.platform.pagination import CursorPage
from app.schemas.tenant import TenantListCursor, TenantListPagination
from app.services.tenant_service import TenantNotFoundError


@dataclass(frozen=True, slots=True)
class PlatformTenantMetadata:
    id: UUID
    slug: str
    name: str
    status: str
    plan_code: str
    data_region: str
    locale: str
    timezone: str
    active_employee_limit: int | None
    created_at: datetime
    updated_at: datetime


class PlatformTenantQueryService:
    """Read platform-safe metadata without importing or querying any HR model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tenant_page(
        self,
        pagination: TenantListPagination | None = None,
    ) -> CursorPage[PlatformTenantMetadata]:
        pagination = pagination or TenantListPagination()
        statement = _metadata_statement().order_by(
            *_tenant_ordering(self.session.get_bind().dialect.name)
        )
        if pagination.cursor is not None:
            statement = statement.where(
                _cursor_predicate(
                    pagination.cursor,
                    dialect_name=self.session.get_bind().dialect.name,
                )
            )
        rows = list((await self.session.execute(statement.limit(pagination.limit + 1))).all())
        items = [_metadata_from_row(row) for row in rows[: pagination.limit]]
        next_cursor = None
        if len(rows) > pagination.limit:
            last_item = items[-1]
            created_at = last_item.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            next_cursor = TenantListCursor(
                created_at=created_at,
                id=last_item.id,
            ).to_token()
        return CursorPage(items=items, next_cursor=next_cursor)

    async def get_tenant(self, tenant_id: UUID) -> PlatformTenantMetadata:
        row = (
            await self.session.execute(
                _metadata_statement().where(Tenant.id == tenant_id)
            )
        ).one_or_none()
        if row is None:
            raise TenantNotFoundError
        return _metadata_from_row(row)


def _metadata_statement():
    return select(
        Tenant.id,
        Tenant.slug,
        Tenant.name,
        Tenant.status,
        Tenant.plan_code,
        Tenant.data_region,
        Tenant.locale,
        Tenant.timezone,
        Tenant.active_employee_limit,
        Tenant.created_at,
        Tenant.updated_at,
    )


def _tenant_ordering(dialect_name: str):
    created_at_key = (
        func.julianday(Tenant.created_at)
        if dialect_name == "sqlite"
        else Tenant.created_at
    )
    return created_at_key.asc(), Tenant.id.asc()


def _cursor_predicate(cursor: TenantListCursor, *, dialect_name: str):
    if dialect_name == "sqlite":
        created_at_key = func.julianday(Tenant.created_at)
        cursor_created_at_key = func.julianday(cursor.created_at)
    else:
        created_at_key = Tenant.created_at
        cursor_created_at_key = cursor.created_at
    return or_(
        created_at_key > cursor_created_at_key,
        and_(
            created_at_key == cursor_created_at_key,
            Tenant.id > cursor.id,
        ),
    )


def _metadata_from_row(row: object) -> PlatformTenantMetadata:
    mapping = row._mapping  # type: ignore[attr-defined]
    return PlatformTenantMetadata(
        id=mapping["id"],
        slug=mapping["slug"],
        name=mapping["name"],
        status=mapping["status"],
        plan_code=mapping["plan_code"],
        data_region=mapping["data_region"],
        locale=mapping["locale"],
        timezone=mapping["timezone"],
        active_employee_limit=mapping["active_employee_limit"],
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
    )


__all__ = ["PlatformTenantMetadata", "PlatformTenantQueryService"]
