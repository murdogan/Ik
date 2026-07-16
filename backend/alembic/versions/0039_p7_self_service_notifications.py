"""Phase 7 self-service, announcements, requests, and notifications.

Revision ID: 0039_p7_self_service_notifications
Revises: 0038_p6_leave_workflow
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    create_tenant_isolation_policy,
    enable_forced_row_security,
    grant_column_privilege,
    grant_table_privileges,
    revoke_all_column_privileges,
    revoke_all_table_privileges,
    revoke_column_privilege,
)

revision = "0039_p7_self_service_notifications"
down_revision = "0038_p6_leave_workflow"
branch_labels = None
depends_on = None

_TENANT_ROLE = "wealthy_falcon_app"
_PLATFORM_ROLE = "wealthy_falcon_platform"
_AUTH_ROLE = "wealthy_falcon_authentication"

_TENANT_TABLES: tuple[str, ...] = (
    "announcements",
    "announcement_role_targets",
    "announcement_department_targets",
    "announcement_branch_targets",
    "announcement_recipients",
    "employee_document_requests",
    "employee_document_request_timeline",
    "notifications",
    "outbox_event_consumptions",
    "notification_deliveries",
    "email_captures",
)

_OUTBOX_COLUMNS: tuple[str, ...] = (
    "id",
    "tenant_id",
    "aggregate_type",
    "aggregate_id",
    "event_type",
    "payload",
    "source_key",
    "occurred_at",
    "created_at",
)

_PERMISSIONS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "request:read:own",
        "request",
        "read",
        "own",
        "Read the current employee's fixed request projection.",
    ),
    (
        "request:read:team",
        "request",
        "read",
        "team",
        "Read team leave requests in the fixed projection.",
    ),
    (
        "request:read:tenant",
        "request",
        "read",
        "tenant",
        "Read the tenant HR request projection.",
    ),
    (
        "document_request:create:own",
        "document_request",
        "create",
        "own",
        "Request an HR-produced document.",
    ),
    (
        "document_request:read:own",
        "document_request",
        "read",
        "own",
        "Read own HR document requests.",
    ),
    (
        "document_request:manage:tenant",
        "document_request",
        "manage",
        "tenant",
        "Resolve tenant document requests.",
    ),
    (
        "announcement:read:own",
        "announcement",
        "read",
        "own",
        "Read announcements snapshotted for this user.",
    ),
    (
        "announcement:manage:tenant",
        "announcement",
        "manage",
        "tenant",
        "Manage and publish tenant announcements.",
    ),
    (
        "notification:read:own",
        "notification",
        "read",
        "own",
        "Read and consume the current user's inbox.",
    ),
    (
        "self_service:read:own",
        "self_service",
        "read",
        "own",
        "Read the employee self-service home.",
    ),
)

_ROLE_GRANTS: tuple[tuple[str, str], ...] = tuple(
    (role_code, permission_code)
    for role_code, permission_codes in {
        "hr_director": (
            "request:read:own",
            "request:read:tenant",
            "document_request:create:own",
            "document_request:read:own",
            "document_request:manage:tenant",
            "announcement:read:own",
            "announcement:manage:tenant",
            "notification:read:own",
            "self_service:read:own",
        ),
        "hr_specialist": (
            "request:read:own",
            "request:read:tenant",
            "document_request:create:own",
            "document_request:read:own",
            "document_request:manage:tenant",
            "announcement:read:own",
            "announcement:manage:tenant",
            "notification:read:own",
            "self_service:read:own",
        ),
        "manager": (
            "request:read:own",
            "request:read:team",
            "document_request:create:own",
            "document_request:read:own",
            "announcement:read:own",
            "notification:read:own",
            "self_service:read:own",
        ),
        "employee": (
            "request:read:own",
            "document_request:create:own",
            "document_request:read:own",
            "announcement:read:own",
            "notification:read:own",
            "self_service:read:own",
        ),
    }.items()
    for permission_code in permission_codes
)


def upgrade() -> None:
    _create_announcements()
    _create_document_requests()
    _create_notifications()
    _baseline_existing_outbox_events()
    _evolve_outbox()
    _create_triggers()
    _configure_rls_and_grants()
    _seed_authorization()
    _enable_rollout()


def _create_announcements() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", name="fk_announcements_tenant", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status in ('draft','published','archived')", name="ck_announcements_status"
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0", name="ck_announcements_title_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(body)) > 0", name="ck_announcements_body_not_blank"
        ),
        sa.CheckConstraint("length(body) <= 10000", name="ck_announcements_body_length"),
        sa.CheckConstraint("version > 0", name="ck_announcements_version_positive"),
        sa.CheckConstraint(
            "(status = 'draft' and published_at is null and published_by_user_id is null "
            "and archived_at is null and archived_by_user_id is null) or "
            "(status = 'published' and published_at is not null "
            "and published_by_user_id is not null and archived_at is null "
            "and archived_by_user_id is null) or "
            "(status = 'archived' and published_at is not null "
            "and published_by_user_id is not null and archived_at is not null "
            "and archived_by_user_id is not null and archived_at >= published_at)",
            name="ck_announcements_lifecycle",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_announcements_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ("tenant_id", "created_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcements_tenant_created_by_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "published_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcements_tenant_published_by_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "archived_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcements_tenant_archived_by_user",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_announcements_tenant_status_created",
        "announcements",
        ("tenant_id", "status", "created_at", "id"),
    )
    op.create_table(
        "announcement_role_targets",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("announcement_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "role_id",
            sa.Uuid(),
            sa.ForeignKey(
                "roles.id", name="fk_announcement_role_targets_role", ondelete="RESTRICT"
            ),
            primary_key=True,
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_role_targets_tenant_announcement",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_announcement_role_targets_tenant_role",
        "announcement_role_targets",
        ("tenant_id", "role_id", "announcement_id"),
    )
    op.create_table(
        "announcement_department_targets",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("announcement_id", sa.Uuid(), primary_key=True),
        sa.Column("department_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_department_targets_tenant_announcement",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "department_id"),
            ("departments.tenant_id", "departments.id"),
            name="fk_announcement_department_targets_tenant_department",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_announcement_department_targets_tenant_department",
        "announcement_department_targets",
        ("tenant_id", "department_id", "announcement_id"),
    )
    op.create_table(
        "announcement_branch_targets",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("announcement_id", sa.Uuid(), primary_key=True),
        sa.Column("branch_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_branch_targets_tenant_announcement",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "branch_id"),
            ("branches.tenant_id", "branches.id"),
            name="fk_announcement_branch_targets_tenant_branch",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_announcement_branch_targets_tenant_branch",
        "announcement_branch_targets",
        ("tenant_id", "branch_id", "announcement_id"),
    )
    op.create_table(
        "announcement_recipients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("announcement_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "version > 0", name="ck_announcement_recipients_version_positive"
        ),
        sa.CheckConstraint(
            "acknowledged_at is null or "
            "(read_at is not null and acknowledged_at >= read_at)",
            name="ck_announcement_recipients_ack_requires_read",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "announcement_id"),
            ("announcements.tenant_id", "announcements.id"),
            name="fk_announcement_recipients_tenant_announcement",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_announcement_recipients_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "announcement_id",
            "recipient_user_id",
            name="uq_announcement_recipients_snapshot",
        ),
    )
    op.create_index(
        "ix_announcement_recipients_user_published",
        "announcement_recipients",
        ("tenant_id", "recipient_user_id", "published_at", "announcement_id"),
    )


def _create_document_requests() -> None:
    op.create_table(
        "employee_document_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey(
                "tenants.id", name="fk_employee_document_requests_tenant", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column("requester_membership_id", sa.Uuid(), nullable=False),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "request_type = 'employment_letter'",
            name="ck_employee_document_requests_type",
        ),
        sa.CheckConstraint(
            "status in ('submitted','resolved','rejected')",
            name="ck_employee_document_requests_status",
        ),
        sa.CheckConstraint(
            "version > 0", name="ck_employee_document_requests_version_positive"
        ),
        sa.CheckConstraint(
            "(status = 'submitted' and decided_at is null and decided_by_user_id is null "
            "and resolution_reason is null) or "
            "(status in ('resolved','rejected') and decided_at is not null "
            "and decided_by_user_id is not null and resolution_reason is not null "
            "and length(trim(resolution_reason)) > 0)",
            name="ck_employee_document_requests_lifecycle",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_employee_document_requests_tenant_id_id"
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "employee_id"),
            ("employees.tenant_id", "employees.id"),
            name="fk_employee_document_requests_tenant_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "requester_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_requests_tenant_requester_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "requester_membership_id"),
            ("tenant_memberships.tenant_id", "tenant_memberships.id"),
            name="fk_employee_document_requests_tenant_requester_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "decided_by_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_requests_tenant_decider_user",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_employee_document_requests_own_cursor",
        "employee_document_requests",
        ("tenant_id", "requester_user_id", "created_at", "id"),
    )
    op.create_index(
        "ix_employee_document_requests_hr_queue",
        "employee_document_requests",
        ("tenant_id", "status", "created_at", "id"),
    )
    op.create_table(
        "employee_document_request_timeline",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type in ('submitted','resolved','rejected')",
            name="ck_employee_document_request_timeline_event",
        ),
        sa.CheckConstraint(
            "event_type = status", name="ck_employee_document_request_timeline_status"
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "request_id"),
            ("employee_document_requests.tenant_id", "employee_document_requests.id"),
            name="fk_employee_document_request_timeline_tenant_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "actor_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_employee_document_request_timeline_tenant_actor",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "source_key", name="uq_employee_document_request_timeline_source"
        ),
    )
    op.create_index(
        "ix_employee_document_request_timeline_request",
        "employee_document_request_timeline",
        ("tenant_id", "request_id", "occurred_at", "id"),
    )


def _create_notifications() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", name="fk_notifications_tenant", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("notification_type", sa.String(96), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("portal_path", sa.String(500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_notifications_version_positive"),
        sa.CheckConstraint(
            "length(trim(notification_type)) > 0", name="ck_notifications_type"
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_notifications_title"),
        sa.CheckConstraint(
            "portal_path like '/%' and portal_path not like '//%'",
            name="ck_notifications_safe_portal_path",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_notifications_tenant_recipient_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("outbox_events.tenant_id", "outbox_events.id"),
            name="fk_notifications_tenant_source_event",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_notifications_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "recipient_user_id",
            name="uq_notifications_event_recipient",
        ),
    )
    op.create_index(
        "ix_notifications_recipient_cursor",
        "notifications",
        ("tenant_id", "recipient_user_id", "created_at", "id"),
    )
    op.create_index(
        "ix_notifications_recipient_unread",
        "notifications",
        ("tenant_id", "recipient_user_id", "read_at", "created_at", "id"),
    )
    op.create_table(
        "outbox_event_consumptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey(
                "tenants.id", name="fk_outbox_event_consumptions_tenant", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "outcome in ('processed','skipped')", name="ck_outbox_event_consumptions_outcome"
        ),
        sa.CheckConstraint(
            "recipient_count >= 0 and recipient_count <= 500",
            name="ck_outbox_event_consumptions_recipient_count",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("outbox_events.tenant_id", "outbox_events.id"),
            name="fk_outbox_event_consumptions_tenant_event",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "source_event_id", name="uq_outbox_event_consumptions_event"
        ),
    )
    op.create_index(
        "ix_outbox_event_consumptions_tenant_created",
        "outbox_event_consumptions",
        ("tenant_id", "created_at", "source_event_id"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_error_code", sa.String(64), nullable=True),
        sa.Column("terminal_error_message", sa.String(200), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "channel in ('in_app','email')", name="ck_notification_deliveries_channel"
        ),
        sa.CheckConstraint(
            "status in ('pending','retry','delivered','failed')",
            name="ck_notification_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 and attempt_count <= 20",
            name="ck_notification_deliveries_attempt_count",
        ),
        sa.CheckConstraint(
            "(status = 'delivered' and delivered_at is not null and next_attempt_at is null "
            "and terminal_error_code is null and terminal_error_message is null) or "
            "(status = 'failed' and delivered_at is null and next_attempt_at is null "
            "and terminal_error_code is not null and terminal_error_message is not null) or "
            "(status in ('pending','retry') and delivered_at is null "
            "and next_attempt_at is not null and terminal_error_code is null "
            "and terminal_error_message is null)",
            name="ck_notification_deliveries_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "notification_id"),
            ("notifications.tenant_id", "notifications.id"),
            name="fk_notification_deliveries_tenant_notification",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "source_event_id"),
            ("outbox_events.tenant_id", "outbox_events.id"),
            name="fk_notification_deliveries_tenant_source_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_notification_deliveries_tenant_recipient_user",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_notification_deliveries_tenant_id_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "recipient_user_id",
            "channel",
            name="uq_notification_deliveries_event_recipient_channel",
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_notification_deliveries_idempotency"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ("tenant_id", "channel", "status", "next_attempt_at", "created_at", "id"),
    )
    op.create_table(
        "email_captures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", name="fk_email_captures_tenant", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("portal_url", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(subject)) > 0", name="ck_email_captures_subject"),
        sa.CheckConstraint(
            "portal_url like 'http://%' or portal_url like 'https://%'",
            name="ck_email_captures_portal_url",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "delivery_id"),
            ("notification_deliveries.tenant_id", "notification_deliveries.id"),
            name="fk_email_captures_tenant_delivery",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ("tenant_id", "recipient_user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_email_captures_tenant_recipient_user",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "delivery_id", name="uq_email_captures_delivery"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_email_captures_idempotency"
        ),
    )
    op.create_index(
        "ix_email_captures_tenant_created",
        "email_captures",
        ("tenant_id", "created_at", "id"),
    )


def _evolve_outbox() -> None:
    op.drop_constraint("ck_outbox_events_event_type", "outbox_events", type_="check")
    op.create_check_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        "event_type in "
        "('leave.requested','leave.approved','leave.rejected','leave.cancelled',"
        "'leave.balance_adjusted','announcement.published')",
    )


def _baseline_existing_outbox_events() -> None:
    """Prevent rollout from turning historical Phase 6 facts into stale user messages."""

    op.execute(
        sa.text(
            """
            INSERT INTO outbox_event_consumptions (
                id, tenant_id, source_event_id, outcome, recipient_count, created_at
            )
            SELECT id, tenant_id, id, 'skipped', 0, now()
            FROM outbox_events
            WHERE event_type IN (
                'leave.requested',
                'leave.approved',
                'leave.rejected',
                'leave.cancelled',
                'leave.balance_adjusted'
            )
            ON CONFLICT (tenant_id, source_event_id) DO NOTHING
            """
        )
    )


def _create_triggers() -> None:
    statements = (
        """
        CREATE OR REPLACE FUNCTION p7_reject_outbox_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'outbox events are immutable' USING ERRCODE = '55000';
        END
        $$
        """,
        "DROP TRIGGER IF EXISTS trg_p7_outbox_immutable ON outbox_events",
        """
        CREATE TRIGGER trg_p7_outbox_immutable
        BEFORE UPDATE OR DELETE ON outbox_events
        FOR EACH ROW EXECUTE FUNCTION p7_reject_outbox_mutation()
        """,
        """
        CREATE OR REPLACE FUNCTION p7_guard_announcement_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status = 'archived' THEN
                RAISE EXCEPTION 'archived announcements are immutable' USING ERRCODE = '55000';
            END IF;
            IF OLD.status = 'published' THEN
                IF NEW.status <> 'archived'
                   OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                   OR NEW.id IS DISTINCT FROM OLD.id
                   OR NEW.title IS DISTINCT FROM OLD.title
                   OR NEW.body IS DISTINCT FROM OLD.body
                   OR NEW.is_critical IS DISTINCT FROM OLD.is_critical
                   OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                   OR NEW.published_by_user_id IS DISTINCT FROM OLD.published_by_user_id
                   OR NEW.published_at IS DISTINCT FROM OLD.published_at
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'published announcement content is immutable'
                        USING ERRCODE = '55000';
                END IF;
            END IF;
            RETURN NEW;
        END
        $$
        """,
        """
        CREATE TRIGGER trg_p7_guard_announcement_update
        BEFORE UPDATE ON announcements
        FOR EACH ROW EXECUTE FUNCTION p7_guard_announcement_update()
        """,
        """
        CREATE OR REPLACE FUNCTION p7_guard_announcement_target()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            target_tenant uuid;
            target_announcement uuid;
            announcement_status varchar;
        BEGIN
            target_tenant := CASE
                WHEN TG_OP = 'DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END;
            target_announcement := CASE
                WHEN TG_OP = 'DELETE' THEN OLD.announcement_id ELSE NEW.announcement_id END;
            SELECT status INTO announcement_status
            FROM announcements
            WHERE tenant_id = target_tenant AND id = target_announcement
            FOR UPDATE;
            IF announcement_status IS DISTINCT FROM 'draft' THEN
                RAISE EXCEPTION 'announcement targets are immutable after publication'
                    USING ERRCODE = '55000';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END
        $$
        """,
        """
        CREATE TRIGGER trg_p7_announcement_role_target
        BEFORE INSERT OR UPDATE OR DELETE ON announcement_role_targets
        FOR EACH ROW EXECUTE FUNCTION p7_guard_announcement_target()
        """,
        """
        CREATE TRIGGER trg_p7_announcement_department_target
        BEFORE INSERT OR UPDATE OR DELETE ON announcement_department_targets
        FOR EACH ROW EXECUTE FUNCTION p7_guard_announcement_target()
        """,
        """
        CREATE TRIGGER trg_p7_announcement_branch_target
        BEFORE INSERT OR UPDATE OR DELETE ON announcement_branch_targets
        FOR EACH ROW EXECUTE FUNCTION p7_guard_announcement_target()
        """,
        """
        CREATE OR REPLACE FUNCTION p7_guard_announcement_recipient()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            publication_status varchar;
            publication_time timestamptz;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                SELECT status, published_at
                INTO publication_status, publication_time
                FROM announcements
                WHERE tenant_id = NEW.tenant_id AND id = NEW.announcement_id
                FOR UPDATE;
                IF publication_status IS DISTINCT FROM 'published'
                   OR publication_time IS DISTINCT FROM NEW.published_at THEN
                    RAISE EXCEPTION 'announcement recipient requires current publication fact'
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.announcement_id IS DISTINCT FROM OLD.announcement_id
               OR NEW.recipient_user_id IS DISTINCT FROM OLD.recipient_user_id
               OR NEW.published_at IS DISTINCT FROM OLD.published_at
               OR (OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at)
               OR (OLD.acknowledged_at IS NOT NULL
                   AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at) THEN
                RAISE EXCEPTION 'announcement recipient snapshot/actions are immutable'
                    USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END
        $$
        """,
        """
        CREATE TRIGGER trg_p7_guard_announcement_recipient
        BEFORE INSERT OR UPDATE ON announcement_recipients
        FOR EACH ROW EXECUTE FUNCTION p7_guard_announcement_recipient()
        """,
    )
    for statement in statements:
        op.execute(sa.text(statement))


def _configure_rls_and_grants() -> None:
    privileges: dict[str, Sequence[str]] = {
        "announcements": ("SELECT", "INSERT"),
        "announcement_role_targets": ("SELECT", "INSERT", "DELETE"),
        "announcement_department_targets": ("SELECT", "INSERT", "DELETE"),
        "announcement_branch_targets": ("SELECT", "INSERT", "DELETE"),
        "announcement_recipients": ("SELECT", "INSERT"),
        "employee_document_requests": ("SELECT", "INSERT"),
        "employee_document_request_timeline": ("SELECT", "INSERT"),
        "notifications": ("SELECT", "INSERT"),
        "outbox_event_consumptions": ("SELECT", "INSERT"),
        "notification_deliveries": ("SELECT", "INSERT"),
        "email_captures": ("SELECT", "INSERT"),
    }
    update_columns: dict[str, Sequence[str]] = {
        "announcements": (
            "title",
            "body",
            "is_critical",
            "status",
            "version",
            "published_by_user_id",
            "published_at",
            "archived_by_user_id",
            "archived_at",
            "updated_at",
        ),
        "announcement_recipients": (
            "read_at",
            "acknowledged_at",
            "version",
        ),
        "employee_document_requests": (
            "status",
            "version",
            "decided_by_user_id",
            "decided_at",
            "resolution_reason",
            "updated_at",
        ),
        "notifications": ("read_at", "version"),
        "notification_deliveries": (
            "status",
            "attempt_count",
            "next_attempt_at",
            "delivered_at",
            "terminal_error_code",
            "terminal_error_message",
            "updated_at",
        ),
    }
    for table_name in _TENANT_TABLES:
        enable_forced_row_security(op, table_name=table_name)
        create_tenant_isolation_policy(
            op,
            table_name=table_name,
            policy_name=f"p7_{table_name}_tenant_isolation",
            role_name=_TENANT_ROLE,
        )
        for role_name in (_TENANT_ROLE, _PLATFORM_ROLE, _AUTH_ROLE):
            revoke_all_table_privileges(op, table_name=table_name, role_name=role_name)
        grant_table_privileges(
            op,
            table_name=table_name,
            role_name=_TENANT_ROLE,
            privileges=privileges[table_name],
        )
        if columns := update_columns.get(table_name):
            grant_column_privilege(
                op,
                table_name=table_name,
                role_name=_TENANT_ROLE,
                privilege="UPDATE",
                column_names=columns,
            )
    for role_name in (_TENANT_ROLE, _PLATFORM_ROLE, _AUTH_ROLE):
        revoke_all_table_privileges(
            op,
            table_name="outbox_events",
            role_name=role_name,
        )
        revoke_all_column_privileges(
            op,
            table_name="outbox_events",
            role_name=role_name,
            column_names=_OUTBOX_COLUMNS,
        )
    grant_table_privileges(
        op,
        table_name="outbox_events",
        role_name=_TENANT_ROLE,
        privileges=("SELECT", "INSERT"),
    )
    grant_column_privilege(
        op,
        table_name="outbox_events",
        role_name=_TENANT_ROLE,
        privilege="UPDATE",
        column_names=("created_at",),
    )


def _seed_authorization() -> None:
    for ordinal, (code, resource, action, target, description) in enumerate(
        _PERMISSIONS, start=41
    ):
        permission_id = f"d3000000-0000-4000-8000-{ordinal:012d}"
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (
                    id, code, resource, action, target, target_type, description,
                    created_at, updated_at
                ) VALUES (
                    CAST(:id AS uuid), :code, :resource, :action, :target, 'scope', :description,
                    now(), now()
                )
                ON CONFLICT (code) DO UPDATE SET
                    resource = EXCLUDED.resource,
                    action = EXCLUDED.action,
                    target = EXCLUDED.target,
                    target_type = EXCLUDED.target_type,
                    description = EXCLUDED.description,
                    updated_at = now()
                """
            ).bindparams(
                id=permission_id,
                code=code,
                resource=resource,
                action=action,
                target=target,
                description=description,
            )
        )
    for role_code, permission_code in _ROLE_GRANTS:
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT roles.id, permissions.id
                FROM roles, permissions
                WHERE roles.code = :role_code
                  AND roles.scope_type = 'tenant'
                  AND permissions.code = :permission_code
                ON CONFLICT DO NOTHING
                """
            ).bindparams(role_code=role_code, permission_code=permission_code)
        )
    role_codes = ("hr_director", "hr_specialist", "manager", "employee")
    op.execute(
        sa.text(
            """
            UPDATE users
            SET permission_version = permission_version + 1, updated_at = now()
            WHERE EXISTS (
                SELECT 1
                FROM user_roles
                JOIN roles ON roles.id = user_roles.role_id
                WHERE user_roles.tenant_id = users.tenant_id
                  AND user_roles.user_id = users.id
                  AND user_roles.active = true
                  AND roles.code = ANY(CAST(:role_codes AS varchar[]))
            )
            """
        ).bindparams(role_codes=list(role_codes))
    )
    op.execute(
        sa.text(
            """
            UPDATE tenant_memberships
            SET permission_version = users.permission_version, updated_at = now()
            FROM users
            WHERE users.tenant_id = tenant_memberships.tenant_id
              AND users.id = tenant_memberships.legacy_user_id
              AND EXISTS (
                  SELECT 1
                  FROM user_roles
                  JOIN roles ON roles.id = user_roles.role_id
                  WHERE user_roles.tenant_id = users.tenant_id
                    AND user_roles.user_id = users.id
                    AND user_roles.active = true
                    AND roles.code = ANY(CAST(:role_codes AS varchar[]))
              )
            """
        ).bindparams(role_codes=list(role_codes))
    )


def _enable_rollout() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO tenant_feature_flags (tenant_id, key, enabled, created_at, updated_at)
            SELECT id, feature_key, true, now(), now()
            FROM tenants
            CROSS JOIN (VALUES ('self_service'), ('notifications')) AS rollout(feature_key)
            ON CONFLICT (tenant_id, key) DO UPDATE
            SET enabled = true, updated_at = now()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_p7_outbox_immutable ON outbox_events"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p7_reject_outbox_mutation()"))
    revoke_column_privilege(
        op,
        table_name="outbox_events",
        role_name=_TENANT_ROLE,
        privilege="UPDATE",
        column_names=("created_at",),
    )
    op.drop_constraint("ck_outbox_events_event_type", "outbox_events", type_="check")
    op.execute(
        sa.text(
            """
            DO $p7_restore_outbox_check$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM outbox_events
                    WHERE event_type = 'announcement.published'
                ) THEN
                    ALTER TABLE outbox_events
                    ADD CONSTRAINT ck_outbox_events_event_type CHECK (
                        event_type IN (
                            'leave.requested', 'leave.approved', 'leave.rejected',
                            'leave.cancelled', 'leave.balance_adjusted',
                            'announcement.published'
                        )
                    );
                ELSE
                    ALTER TABLE outbox_events
                    ADD CONSTRAINT ck_outbox_events_event_type CHECK (
                        event_type IN (
                            'leave.requested', 'leave.approved', 'leave.rejected',
                            'leave.cancelled', 'leave.balance_adjusted'
                        )
                    );
                END IF;
            END
            $p7_restore_outbox_check$;
            """
        )
    )
    for table_name in reversed(_TENANT_TABLES):
        op.drop_table(table_name)
    op.execute(sa.text("DROP FUNCTION IF EXISTS p7_guard_announcement_recipient()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p7_guard_announcement_target()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS p7_guard_announcement_update()"))
    for role_code, permission_code in _ROLE_GRANTS:
        op.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                USING roles, permissions
                WHERE role_permissions.role_id = roles.id
                  AND role_permissions.permission_id = permissions.id
                  AND roles.code = :role_code
                  AND permissions.code = :permission_code
                """
            ).bindparams(role_code=role_code, permission_code=permission_code)
        )
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(CAST(:codes AS varchar[]))").bindparams(
            codes=[permission[0] for permission in _PERMISSIONS]
        )
    )
