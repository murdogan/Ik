"""close the P3K legacy tenant authentication boundary

Revision ID: 0031_p3k_legacy_tenant_auth_boundary
Revises: 0030_p3i_employee_assignments
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_p3k_legacy_tenant_auth_boundary"
down_revision: str | None = "0030_p3i_employee_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSIONS_TABLE = "permissions"
_ROLE_PERMISSIONS_TABLE = "role_permissions"
_ROLES_TABLE = "roles"

_LEAVE_MANAGE_PERMISSION_ID = UUID("d3000000-0000-4000-8000-000000000033")
_LEAVE_MANAGE_PERMISSION_CODE = "leave:manage:tenant"
_LEAVE_MANAGE_PERMISSION_DESCRIPTION = "Manage leave requests across the current tenant."
_HR_DIRECTOR_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000003")
_HR_SPECIALIST_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000004")
_EXPECTED_ROLE_IDS = frozenset((_HR_DIRECTOR_ROLE_ID, _HR_SPECIALIST_ROLE_ID))

_UUID = postgresql.UUID(as_uuid=True)
_permissions = sa.table(
    _PERMISSIONS_TABLE,
    sa.column("id", _UUID),
    sa.column("code", sa.String()),
    sa.column("resource", sa.String()),
    sa.column("action", sa.String()),
    sa.column("target", sa.String()),
    sa.column("target_type", sa.String()),
    sa.column("description", sa.Text()),
)
_roles = sa.table(
    _ROLES_TABLE,
    sa.column("id", _UUID),
)
_role_permissions = sa.table(
    _ROLE_PERMISSIONS_TABLE,
    sa.column("role_id", _UUID),
    sa.column("permission_id", _UUID),
)


def upgrade() -> None:
    if op.get_context().as_sql:
        op.bulk_insert(
            _permissions,
            [
                {
                    "id": _LEAVE_MANAGE_PERMISSION_ID,
                    "code": _LEAVE_MANAGE_PERMISSION_CODE,
                    "resource": "leave",
                    "action": "manage",
                    "target": "tenant",
                    "target_type": "scope",
                    "description": _LEAVE_MANAGE_PERMISSION_DESCRIPTION,
                }
            ],
            multiinsert=False,
        )
        op.bulk_insert(
            _role_permissions,
            [
                {
                    "role_id": role_id,
                    "permission_id": _LEAVE_MANAGE_PERMISSION_ID,
                }
                for role_id in sorted(_EXPECTED_ROLE_IDS, key=str)
            ],
            multiinsert=False,
        )
        return

    bind = op.get_bind()
    matching_permissions = (
        bind.execute(
            sa.select(_permissions).where(
                sa.or_(
                    _permissions.c.id == _LEAVE_MANAGE_PERMISSION_ID,
                    _permissions.c.code == _LEAVE_MANAGE_PERMISSION_CODE,
                )
            )
        )
        .mappings()
        .all()
    )

    expected_permission = {
        "id": _LEAVE_MANAGE_PERMISSION_ID,
        "code": _LEAVE_MANAGE_PERMISSION_CODE,
        "resource": "leave",
        "action": "manage",
        "target": "tenant",
        "target_type": "scope",
        "description": _LEAVE_MANAGE_PERMISSION_DESCRIPTION,
    }
    if matching_permissions:
        if len(matching_permissions) != 1 or any(
            matching_permissions[0][column] != value
            for column, value in expected_permission.items()
        ):
            raise RuntimeError("P3K permission catalog conflict for leave:manage:tenant")
    else:
        op.execute(sa.insert(_permissions).values(expected_permission))

    existing_role_ids = frozenset(
        bind.execute(sa.select(_roles.c.id).where(_roles.c.id.in_(_EXPECTED_ROLE_IDS))).scalars()
    )
    if existing_role_ids != _EXPECTED_ROLE_IDS:
        raise RuntimeError("P3K leave management roles are missing from the catalog")

    existing_grants = frozenset(
        bind.execute(
            sa.select(_role_permissions.c.role_id).where(
                _role_permissions.c.permission_id == _LEAVE_MANAGE_PERMISSION_ID
            )
        ).scalars()
    )
    unexpected_grants = existing_grants - _EXPECTED_ROLE_IDS
    if unexpected_grants:
        raise RuntimeError("P3K leave management permission has unexpected role grants")
    for role_id in _EXPECTED_ROLE_IDS - existing_grants:
        op.execute(
            sa.insert(_role_permissions).values(
                role_id=role_id,
                permission_id=_LEAVE_MANAGE_PERMISSION_ID,
            )
        )


def downgrade() -> None:
    if op.get_context().as_sql:
        op.execute(
            sa.delete(_role_permissions).where(
                _role_permissions.c.permission_id == _LEAVE_MANAGE_PERMISSION_ID,
                _role_permissions.c.role_id.in_(_EXPECTED_ROLE_IDS),
            )
        )
        op.execute(
            sa.delete(_permissions).where(
                _permissions.c.id == _LEAVE_MANAGE_PERMISSION_ID,
                _permissions.c.code == _LEAVE_MANAGE_PERMISSION_CODE,
            )
        )
        return

    bind = op.get_bind()
    existing_grants = frozenset(
        bind.execute(
            sa.select(_role_permissions.c.role_id).where(
                _role_permissions.c.permission_id == _LEAVE_MANAGE_PERMISSION_ID
            )
        ).scalars()
    )
    if existing_grants - _EXPECTED_ROLE_IDS:
        raise RuntimeError("P3K downgrade refused: leave management permission has retained grants")

    op.execute(
        sa.delete(_role_permissions).where(
            _role_permissions.c.permission_id == _LEAVE_MANAGE_PERMISSION_ID,
            _role_permissions.c.role_id.in_(_EXPECTED_ROLE_IDS),
        )
    )
    op.execute(
        sa.delete(_permissions).where(
            _permissions.c.id == _LEAVE_MANAGE_PERMISSION_ID,
            _permissions.c.code == _LEAVE_MANAGE_PERMISSION_CODE,
        )
    )


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
