"""Provision the initial tenant administrator through one platform gateway.

Revision ID: 0044_platform_initial_tenant_admin
Revises: 0043_p11_employee_lifecycle_profile_lock
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.platform.db.rls_migration import (
    disable_forced_row_security,
    drop_policy,
    enable_forced_row_security,
    grant_column_privilege,
    revoke_column_privilege,
)
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)

revision: str = "0044_platform_initial_tenant_admin"
down_revision: str | None = "0043_p11_employee_lifecycle_profile_lock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECTION_ROLE = "wealthy_falcon_identity_projection"
_FUNCTION_NAME = "provision_platform_initial_tenant_admin"
_FUNCTION_SIGNATURE = (
    "public.provision_platform_initial_tenant_admin(uuid,uuid,text,text,uuid,text,timestamptz,uuid)"
)
_REISSUE_FUNCTION_NAME = "reissue_platform_initial_tenant_admin_invitation"
_REISSUE_FUNCTION_SIGNATURE = (
    "public.reissue_platform_initial_tenant_admin_invitation(uuid,uuid,text,timestamptz,uuid)"
)
_CORRECTION_FUNCTION_NAME = "correct_platform_initial_tenant_admin_invitation"
_CORRECTION_FUNCTION_SIGNATURE = (
    "public.correct_platform_initial_tenant_admin_invitation("
    "uuid,text,text,uuid,uuid,text,timestamptz,uuid)"
)
_TENANT_ADMIN_ROLE_ID = "d2000000-0000-4000-8000-000000000002"
_INVITATION_EVENT_TYPE = "identity.initial_admin_invited"
_OUTBOX_CHECK = "ck_outbox_events_event_type"
_DELIVERY_LEASE_CHECK = "ck_notification_deliveries_lease"
_DELIVERY_PREPARED_MESSAGE_CHECK = "ck_notification_deliveries_prepared_message"
_DELIVERY_UPDATE_COLUMNS = (
    "lease_id",
    "lease_expires_at",
    "lease_attempt",
    "prepared_recipient_email",
    "prepared_subject",
    "prepared_body_prefix",
    "prepared_frontend_base_url",
    "prepared_portal_path",
    "prepared_message_id",
    "prepared_activation_id",
)
_POLICIES = (
    ("tenants", "platform_initial_admin_tenant_read"),
    ("users", "platform_initial_admin_user_insert"),
    ("users", "platform_initial_admin_user_update"),
    ("user_roles", "platform_initial_admin_user_role_insert"),
    ("user_activation_tokens", "platform_initial_admin_activation_insert"),
    ("user_activation_tokens", "platform_initial_admin_activation_select"),
    ("user_activation_tokens", "platform_initial_admin_activation_update"),
    ("outbox_events", "platform_initial_admin_outbox_insert"),
    ("outbox_events", "platform_initial_admin_outbox_select"),
    ("outbox_events", "tenant_initial_admin_event_guard"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    _add_notification_delivery_lifecycle()
    _extend_outbox_event_contract()
    _assert_projection_owner_is_safe()
    _create_projection_policies()
    _grant_projection_columns()
    _create_gateway()


def _add_notification_delivery_lifecycle() -> None:
    columns = (
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_attempt", sa.Integer(), nullable=True),
        sa.Column("prepared_recipient_email", sa.String(320), nullable=True),
        sa.Column("prepared_subject", sa.String(200), nullable=True),
        sa.Column("prepared_body_prefix", sa.Text(), nullable=True),
        sa.Column("prepared_frontend_base_url", sa.Text(), nullable=True),
        sa.Column("prepared_portal_path", sa.String(500), nullable=True),
        sa.Column("prepared_message_id", sa.String(320), nullable=True),
        sa.Column("prepared_activation_id", sa.Uuid(), nullable=True),
    )
    for column in columns:
        op.add_column("notification_deliveries", column)
    op.create_check_constraint(
        _DELIVERY_LEASE_CHECK,
        "notification_deliveries",
        "(lease_id is null and lease_expires_at is null and lease_attempt is null) or "
        "(lease_id is not null and lease_expires_at is not null "
        "and lease_attempt = attempt_count "
        "and channel = 'email' and status in ('pending','retry'))",
    )
    op.create_check_constraint(
        _DELIVERY_PREPARED_MESSAGE_CHECK,
        "notification_deliveries",
        "(prepared_recipient_email is null and prepared_subject is null "
        "and prepared_body_prefix is null and prepared_frontend_base_url is null "
        "and prepared_portal_path is null and prepared_message_id is null "
        "and prepared_activation_id is null) or "
        "(channel = 'email' and prepared_recipient_email is not null "
        "and prepared_subject is not null and prepared_body_prefix is not null "
        "and prepared_frontend_base_url is not null "
        "and prepared_portal_path is not null and prepared_message_id is not null)",
    )
    grant_column_privilege(
        op,
        table_name="notification_deliveries",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_DELIVERY_UPDATE_COLUMNS,
    )


def _extend_outbox_event_contract() -> None:
    op.drop_constraint(_OUTBOX_CHECK, "outbox_events", type_="check")
    op.create_check_constraint(
        _OUTBOX_CHECK,
        "outbox_events",
        "event_type in "
        "('leave.requested','leave.approved','leave.rejected','leave.cancelled',"
        "'leave.balance_adjusted','announcement.published',"
        f"'{_INVITATION_EVENT_TYPE}')",
    )


def _assert_projection_owner_is_safe() -> None:
    op.execute(
        sa.text(
            f"""
            DO $platform_initial_admin_owner_preflight$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = '{_PROJECTION_ROLE}'
                      AND rolcanlogin = false
                      AND rolsuper = false
                      AND rolcreatedb = false
                      AND rolcreaterole = false
                      AND rolinherit = false
                      AND rolbypassrls = false
                      AND rolreplication = false
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.member
                    WHERE owner_role.rolname = '{_PROJECTION_ROLE}'
                ) OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS owner_role
                      ON owner_role.oid = membership.roleid
                    JOIN pg_catalog.pg_roles AS member_role
                      ON member_role.oid = membership.member
                    WHERE owner_role.rolname = '{_PROJECTION_ROLE}'
                      AND member_role.rolname <> current_user
                ) THEN
                    RAISE EXCEPTION
                        'Platform initial-admin owner preflight failed';
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_roles
                    WHERE rolname = current_user
                      AND (
                          rolsuper = true
                          OR pg_catalog.pg_has_role(
                              current_user, '{_PROJECTION_ROLE}', 'SET'
                          )
                      )
                ) OR pg_catalog.has_schema_privilege(
                    '{_PROJECTION_ROLE}', 'public', 'CREATE'
                ) THEN
                    RAISE EXCEPTION
                        'Platform initial-admin ownership transfer is unsafe';
                END IF;
            END
            $platform_initial_admin_owner_preflight$
            """
        )
    )


def _create_projection_policies() -> None:
    tenant_predicate = (
        "tenant_id = nullif(pg_catalog.current_setting('app.tenant_id', true), '')::uuid"
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[0][1]}" ON public.tenants
            AS PERMISSIVE FOR SELECT TO "{_PROJECTION_ROLE}"
            USING (
                id = nullif(
                    pg_catalog.current_setting('app.tenant_id', true), ''
                )::uuid
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[1][1]}" ON public.users
            AS PERMISSIVE FOR INSERT TO "{_PROJECTION_ROLE}"
            WITH CHECK (
                {tenant_predicate}
                AND status = 'invited'
                AND password_hash IS NULL
                AND can_invite_users IS FALSE
                AND permission_version = 1
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[2][1]}" ON public.users
            AS PERMISSIVE FOR UPDATE TO "{_PROJECTION_ROLE}"
            USING (
                {tenant_predicate}
                AND status = 'invited'
                AND password_hash IS NULL
            )
            WITH CHECK (
                {tenant_predicate}
                AND status = 'invited'
                AND password_hash IS NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[3][1]}" ON public.user_roles
            AS PERMISSIVE FOR INSERT TO "{_PROJECTION_ROLE}"
            WITH CHECK (
                {tenant_predicate}
                AND role_id = '{_TENANT_ADMIN_ROLE_ID}'::uuid
                AND role_scope_type = 'tenant'
                AND active IS TRUE
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[4][1]}" ON public.user_activation_tokens
            AS PERMISSIVE FOR INSERT TO "{_PROJECTION_ROLE}"
            WITH CHECK ({tenant_predicate})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[5][1]}" ON public.user_activation_tokens
            AS PERMISSIVE FOR SELECT TO "{_PROJECTION_ROLE}"
            USING ({tenant_predicate})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[6][1]}" ON public.user_activation_tokens
            AS PERMISSIVE FOR UPDATE TO "{_PROJECTION_ROLE}"
            USING ({tenant_predicate})
            WITH CHECK ({tenant_predicate})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[7][1]}" ON public.outbox_events
            AS PERMISSIVE FOR INSERT TO "{_PROJECTION_ROLE}"
            WITH CHECK (
                {tenant_predicate}
                AND aggregate_type = 'identity_membership'
                AND event_type = '{_INVITATION_EVENT_TYPE}'
                AND source_key IN (
                    '{_INVITATION_EVENT_TYPE}:' || aggregate_id::text,
                    '{_INVITATION_EVENT_TYPE}:' || aggregate_id::text
                        || ':reissue:' || (payload ->> 'activation_id'),
                    '{_INVITATION_EVENT_TYPE}:' || aggregate_id::text
                        || ':correction:' || (payload ->> 'activation_id')
                )
                AND pg_catalog.jsonb_typeof(payload) = 'object'
                AND payload ? 'recipient_user_id'
                AND payload ? 'activation_id'
                AND payload - 'recipient_user_id' - 'activation_id' = '{{}}'::jsonb
                AND payload ->> 'recipient_user_id' = aggregate_id::text
                AND payload ->> 'activation_id' ~
                    '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-'
                    '[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[8][1]}" ON public.outbox_events
            AS PERMISSIVE FOR SELECT TO "{_PROJECTION_ROLE}"
            USING ({tenant_predicate})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "{_POLICIES[9][1]}" ON public.outbox_events
            AS RESTRICTIVE FOR INSERT TO "{TENANT_APPLICATION_ROLE}"
            WITH CHECK (event_type <> 'identity.initial_admin_invited')
            """
        )
    )


def _grant_projection_columns() -> None:
    grants = (
        ("tenants", "SELECT", ("id", "status")),
        (
            "users",
            "INSERT",
            (
                "id",
                "tenant_id",
                "email",
                "full_name",
                "status",
                "password_hash",
                "can_invite_users",
                "permission_version",
            ),
        ),
        (
            "users",
            "UPDATE",
            (
                "email",
                "full_name",
                "updated_at",
            ),
        ),
        (
            "user_roles",
            "INSERT",
            (
                "tenant_id",
                "user_id",
                "role_id",
                "role_scope_type",
                "active",
                "created_at",
                "updated_at",
            ),
        ),
        (
            "user_activation_tokens",
            "INSERT",
            ("id", "tenant_id", "user_id", "token_hash", "expires_at"),
        ),
        (
            "user_activation_tokens",
            "SELECT",
            ("id", "tenant_id", "user_id", "consumed_at", "revoked_at"),
        ),
        (
            "user_activation_tokens",
            "UPDATE",
            ("revoked_at", "updated_at"),
        ),
        (
            "outbox_events",
            "INSERT",
            (
                "id",
                "tenant_id",
                "aggregate_type",
                "aggregate_id",
                "event_type",
                "payload",
                "source_key",
                "occurred_at",
            ),
        ),
        (
            "outbox_events",
            "SELECT",
            (
                "tenant_id",
                "aggregate_type",
                "aggregate_id",
                "event_type",
                "payload",
                "source_key",
            ),
        ),
    )
    for table_name, privilege, columns in grants:
        grant_column_privilege(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
            privilege=privilege,
            column_names=columns,
        )


def _create_gateway() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_FUNCTION_NAME}(
                requested_tenant_id uuid,
                requested_user_id uuid,
                requested_full_name text,
                requested_email text,
                requested_activation_id uuid,
                requested_token_hash text,
                requested_expires_at timestamptz,
                requested_outbox_id uuid
            )
            RETURNS void
            LANGUAGE plpgsql
            VOLATILE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $platform_initial_admin$
            DECLARE
                previous_tenant_context text;
                canonical_status text;
            BEGIN
                previous_tenant_context := pg_catalog.current_setting(
                    'app.tenant_id', true
                );
                IF nullif(previous_tenant_context, '') IS NOT NULL
                   OR requested_tenant_id IS NULL
                   OR requested_tenant_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_user_id IS NULL
                   OR requested_user_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_activation_id IS NULL
                   OR requested_activation_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_outbox_id IS NULL
                   OR requested_outbox_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_full_name <> pg_catalog.btrim(requested_full_name)
                   OR pg_catalog.char_length(requested_full_name) NOT BETWEEN 1 AND 200
                   OR requested_email <> pg_catalog.lower(
                       pg_catalog.btrim(requested_email)
                   )
                   OR pg_catalog.char_length(requested_email) NOT BETWEEN 3 AND 320
                   OR requested_email !~ '^[^@[:space:]]+@[^@[:space:]]+$'
                   OR requested_token_hash !~ '^[0-9a-f]{{64}}$'
                   OR requested_expires_at <= pg_catalog.clock_timestamp()
                   OR requested_expires_at > (
                       pg_catalog.clock_timestamp() + interval '168 hours'
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_roles AS login_role
                       WHERE login_role.rolname = session_user
                         AND login_role.rolcanlogin IS TRUE
                         AND (
                             login_role.rolsuper IS TRUE
                             OR (
                                 login_role.rolbypassrls IS FALSE
                                 AND pg_catalog.pg_has_role(
                                     session_user,
                                     '{PLATFORM_APPLICATION_ROLE}',
                                     'SET'
                                 )
                             )
                         )
                   ) THEN
                    RAISE EXCEPTION 'Initial administrator is unavailable'
                        USING ERRCODE = 'WF003';
                END IF;

                PERFORM pg_catalog.set_config(
                    'app.tenant_id', requested_tenant_id::text, true
                );
                BEGIN
                    PERFORM pg_catalog.pg_advisory_xact_lock(
                        pg_catalog.hashtextextended(requested_tenant_id::text, 11044)
                    );
                    PERFORM tenants.id
                    FROM public.tenants AS tenants
                    WHERE tenants.id = requested_tenant_id
                      AND tenants.status = 'provisioning';
                    IF NOT FOUND OR EXISTS (
                        SELECT 1
                        FROM public.users AS users
                        WHERE users.tenant_id = requested_tenant_id
                    ) THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    PERFORM pg_catalog.pg_advisory_xact_lock(
                        pg_catalog.hashtextextended(requested_email, 11044)
                    );
                    SELECT identities.status INTO canonical_status
                    FROM public.identities AS identities
                    WHERE identities.email_normalized = requested_email
                    FOR UPDATE;
                    IF canonical_status IS NOT NULL
                       AND canonical_status NOT IN ('pending', 'active') THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    INSERT INTO public.users (
                        id, tenant_id, email, full_name, status, password_hash,
                        can_invite_users, permission_version
                    ) VALUES (
                        requested_user_id, requested_tenant_id, requested_email,
                        requested_full_name, 'invited', NULL, false, 1
                    );
                    INSERT INTO public.user_roles (
                        tenant_id, user_id, role_id, role_scope_type, active,
                        created_at, updated_at
                    ) VALUES (
                        requested_tenant_id, requested_user_id,
                        '{_TENANT_ADMIN_ROLE_ID}'::uuid, 'tenant', true,
                        pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
                    );

                    PERFORM public.sync_current_tenant_identity_membership(
                        requested_user_id, false
                    );

                    INSERT INTO public.user_activation_tokens (
                        id, tenant_id, user_id, token_hash, expires_at
                    ) VALUES (
                        requested_activation_id, requested_tenant_id,
                        requested_user_id, requested_token_hash,
                        requested_expires_at
                    );
                    INSERT INTO public.outbox_events (
                        id, tenant_id, aggregate_type, aggregate_id, event_type,
                        payload, source_key, occurred_at
                    ) VALUES (
                        requested_outbox_id, requested_tenant_id,
                        'identity_membership', requested_user_id,
                        '{_INVITATION_EVENT_TYPE}',
                        pg_catalog.jsonb_build_object(
                            'recipient_user_id', requested_user_id::text,
                            'activation_id', requested_activation_id::text
                        ),
                        '{_INVITATION_EVENT_TYPE}:' || requested_user_id::text,
                        pg_catalog.clock_timestamp()
                    );
                EXCEPTION WHEN OTHERS THEN
                    PERFORM pg_catalog.set_config(
                        'app.tenant_id',
                        coalesce(previous_tenant_context, ''),
                        true
                    );
                    RAISE;
                END;
                PERFORM pg_catalog.set_config(
                    'app.tenant_id',
                    coalesce(previous_tenant_context, ''),
                    true
                );
            END
            $platform_initial_admin$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_REISSUE_FUNCTION_NAME}(
                requested_tenant_id uuid,
                requested_activation_id uuid,
                requested_token_hash text,
                requested_expires_at timestamptz,
                requested_outbox_id uuid
            )
            RETURNS void
            LANGUAGE plpgsql
            VOLATILE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $platform_initial_admin_reissue$
            DECLARE
                previous_tenant_context text;
                canonical_tenant_status text;
                original_invitation_count bigint;
                original_user_id uuid;
                original_activation_id uuid;
                local_user_status text;
                local_password_hash text;
                membership_identity_id uuid;
                membership_status text;
                canonical_identity_status text;
                active_user_role_count bigint;
                active_user_tenant_admin_count bigint;
                active_membership_role_count bigint;
                active_membership_tenant_admin_count bigint;
                consumed_activation_count bigint;
                original_activation_count bigint;
                rotated_at timestamptz;
            BEGIN
                previous_tenant_context := pg_catalog.current_setting(
                    'app.tenant_id', true
                );
                IF nullif(previous_tenant_context, '') IS NOT NULL
                   OR requested_tenant_id IS NULL
                   OR requested_tenant_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_activation_id IS NULL
                   OR requested_activation_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_outbox_id IS NULL
                   OR requested_outbox_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_token_hash IS NULL
                   OR requested_token_hash !~ '^[0-9a-f]{{64}}$'
                   OR requested_expires_at IS NULL
                   OR requested_expires_at <= pg_catalog.clock_timestamp()
                   OR requested_expires_at > (
                       pg_catalog.clock_timestamp() + interval '168 hours'
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_roles AS login_role
                       WHERE login_role.rolname = session_user
                         AND login_role.rolcanlogin IS TRUE
                         AND (
                             login_role.rolsuper IS TRUE
                             OR (
                                 login_role.rolbypassrls IS FALSE
                                 AND pg_catalog.pg_has_role(
                                     session_user,
                                     '{PLATFORM_APPLICATION_ROLE}',
                                     'SET'
                                 )
                             )
                         )
                   ) THEN
                    RAISE EXCEPTION 'Initial administrator is unavailable'
                        USING ERRCODE = 'WF003';
                END IF;

                PERFORM pg_catalog.set_config(
                    'app.tenant_id', requested_tenant_id::text, true
                );
                BEGIN
                    PERFORM pg_catalog.pg_advisory_xact_lock(
                        pg_catalog.hashtextextended(requested_tenant_id::text, 11044)
                    );

                    SELECT tenants.status INTO canonical_tenant_status
                    FROM public.tenants AS tenants
                    WHERE tenants.id = requested_tenant_id;
                    IF NOT FOUND
                       OR canonical_tenant_status NOT IN (
                           'provisioning', 'trial', 'active'
                       ) THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT
                        pg_catalog.count(events.aggregate_id),
                        pg_catalog.min(events.aggregate_id::text)::uuid,
                        pg_catalog.min(events.payload ->> 'activation_id')::uuid
                    INTO
                        original_invitation_count,
                        original_user_id,
                        original_activation_id
                    FROM public.outbox_events AS events
                    WHERE events.tenant_id = requested_tenant_id
                      AND events.aggregate_type = 'identity_membership'
                      AND events.event_type = '{_INVITATION_EVENT_TYPE}'
                      AND events.source_key = '{_INVITATION_EVENT_TYPE}:'
                          || events.aggregate_id::text
                      AND pg_catalog.jsonb_typeof(events.payload) = 'object'
                      AND events.payload ? 'recipient_user_id'
                      AND events.payload ? 'activation_id'
                      AND events.payload
                          - 'recipient_user_id' - 'activation_id' = '{{}}'::jsonb
                      AND events.payload ->> 'recipient_user_id'
                          = events.aggregate_id::text
                      AND events.payload ->> 'activation_id' ~
                          '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-'
                          '[0-9a-f]{{4}}-[0-9a-f]{{12}}$';
                    IF original_invitation_count <> 1
                       OR original_user_id IS NULL
                       OR original_user_id
                           = '00000000-0000-0000-0000-000000000000'::uuid
                       OR original_activation_id IS NULL
                       OR original_activation_id
                           = '00000000-0000-0000-0000-000000000000'::uuid THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    PERFORM tokens.id
                    FROM public.user_activation_tokens AS tokens
                    WHERE tokens.tenant_id = requested_tenant_id
                      AND tokens.user_id = original_user_id
                    FOR UPDATE;
                    SELECT
                        pg_catalog.count(tokens.id) FILTER (
                            WHERE tokens.consumed_at IS NOT NULL
                        ),
                        pg_catalog.count(tokens.id) FILTER (
                            WHERE tokens.id = original_activation_id
                        )
                    INTO consumed_activation_count, original_activation_count
                    FROM public.user_activation_tokens AS tokens
                    WHERE tokens.tenant_id = requested_tenant_id
                      AND tokens.user_id = original_user_id;
                    IF consumed_activation_count <> 0
                       OR original_activation_count <> 1 THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT users.status, users.password_hash
                    INTO local_user_status, local_password_hash
                    FROM public.users AS users
                    WHERE users.tenant_id = requested_tenant_id
                      AND users.id = original_user_id;
                    IF NOT FOUND
                       OR local_user_status <> 'invited'
                       OR local_password_hash IS NOT NULL THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT memberships.identity_id, memberships.status
                    INTO membership_identity_id, membership_status
                    FROM public.tenant_memberships AS memberships
                    WHERE memberships.tenant_id = requested_tenant_id
                      AND memberships.id = original_user_id
                      AND memberships.legacy_user_id = original_user_id;
                    IF NOT FOUND OR membership_status <> 'invited' THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT identities.status INTO canonical_identity_status
                    FROM public.identities AS identities
                    WHERE identities.id = membership_identity_id;
                    IF NOT FOUND
                       OR canonical_identity_status NOT IN ('pending', 'active') THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT
                        pg_catalog.count(roles.role_id),
                        pg_catalog.count(roles.role_id) FILTER (
                            WHERE roles.role_id = '{_TENANT_ADMIN_ROLE_ID}'::uuid
                              AND roles.role_scope_type = 'tenant'
                        )
                    INTO active_user_role_count, active_user_tenant_admin_count
                    FROM public.user_roles AS roles
                    WHERE roles.tenant_id = requested_tenant_id
                      AND roles.user_id = original_user_id
                      AND roles.active IS TRUE;
                    SELECT
                        pg_catalog.count(roles.role_id),
                        pg_catalog.count(roles.role_id) FILTER (
                            WHERE roles.role_id = '{_TENANT_ADMIN_ROLE_ID}'::uuid
                              AND roles.role_scope_type = 'tenant'
                        )
                    INTO
                        active_membership_role_count,
                        active_membership_tenant_admin_count
                    FROM public.membership_roles AS roles
                    WHERE roles.tenant_id = requested_tenant_id
                      AND roles.membership_id = original_user_id
                      AND roles.active IS TRUE;
                    IF active_user_role_count <> 1
                       OR active_user_tenant_admin_count <> 1
                       OR active_membership_role_count <> 1
                       OR active_membership_tenant_admin_count <> 1 THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    rotated_at := pg_catalog.clock_timestamp();
                    UPDATE public.user_activation_tokens AS tokens
                    SET revoked_at = rotated_at,
                        updated_at = rotated_at
                    WHERE tokens.tenant_id = requested_tenant_id
                      AND tokens.user_id = original_user_id
                      AND tokens.consumed_at IS NULL
                      AND tokens.revoked_at IS NULL;

                    INSERT INTO public.user_activation_tokens (
                        id, tenant_id, user_id, token_hash, expires_at
                    ) VALUES (
                        requested_activation_id, requested_tenant_id,
                        original_user_id, requested_token_hash,
                        requested_expires_at
                    );
                    INSERT INTO public.outbox_events (
                        id, tenant_id, aggregate_type, aggregate_id, event_type,
                        payload, source_key, occurred_at
                    ) VALUES (
                        requested_outbox_id, requested_tenant_id,
                        'identity_membership', original_user_id,
                        '{_INVITATION_EVENT_TYPE}',
                        pg_catalog.jsonb_build_object(
                            'recipient_user_id', original_user_id::text,
                            'activation_id', requested_activation_id::text
                        ),
                        '{_INVITATION_EVENT_TYPE}:' || original_user_id::text
                            || ':reissue:' || requested_activation_id::text,
                        rotated_at
                    );
                EXCEPTION WHEN OTHERS THEN
                    PERFORM pg_catalog.set_config(
                        'app.tenant_id',
                        coalesce(previous_tenant_context, ''),
                        true
                    );
                    RAISE;
                END;
                PERFORM pg_catalog.set_config(
                    'app.tenant_id',
                    coalesce(previous_tenant_context, ''),
                    true
                );
            END
            $platform_initial_admin_reissue$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION public.{_CORRECTION_FUNCTION_NAME}(
                requested_tenant_id uuid,
                requested_full_name text,
                requested_email text,
                requested_identity_id uuid,
                requested_activation_id uuid,
                requested_token_hash text,
                requested_expires_at timestamptz,
                requested_outbox_id uuid
            )
            RETURNS void
            LANGUAGE plpgsql
            VOLATILE
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $platform_initial_admin_correction$
            DECLARE
                previous_tenant_context text;
                canonical_tenant_status text;
                original_invitation_count bigint;
                original_user_id uuid;
                original_activation_id uuid;
                local_user_status text;
                local_user_email text;
                local_password_hash text;
                membership_identity_id uuid;
                membership_status text;
                old_identity_status text;
                old_identity_email text;
                target_identity_id uuid;
                target_identity_status text;
                conflicting_membership_count bigint;
                duplicate_user_count bigint;
                active_user_role_count bigint;
                active_user_tenant_admin_count bigint;
                active_membership_role_count bigint;
                active_membership_tenant_admin_count bigint;
                consumed_activation_count bigint;
                original_activation_count bigint;
                corrected_at timestamptz;
            BEGIN
                previous_tenant_context := pg_catalog.current_setting(
                    'app.tenant_id', true
                );
                IF nullif(previous_tenant_context, '') IS NOT NULL
                   OR requested_tenant_id IS NULL
                   OR requested_tenant_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_identity_id IS NULL
                   OR requested_identity_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_activation_id IS NULL
                   OR requested_activation_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_outbox_id IS NULL
                   OR requested_outbox_id = '00000000-0000-0000-0000-000000000000'::uuid
                   OR requested_full_name IS NULL
                   OR requested_full_name <> pg_catalog.btrim(requested_full_name)
                   OR pg_catalog.char_length(requested_full_name) NOT BETWEEN 1 AND 200
                   OR requested_email IS NULL
                   OR requested_email <> pg_catalog.lower(
                       pg_catalog.btrim(requested_email)
                   )
                   OR pg_catalog.char_length(requested_email) NOT BETWEEN 3 AND 320
                   OR requested_email !~ '^[^@[:space:]]+@[^@[:space:]]+$'
                   OR requested_token_hash IS NULL
                   OR requested_token_hash !~ '^[0-9a-f]{{64}}$'
                   OR requested_expires_at IS NULL
                   OR requested_expires_at <= pg_catalog.clock_timestamp()
                   OR requested_expires_at > (
                       pg_catalog.clock_timestamp() + interval '168 hours'
                   )
                   OR NOT EXISTS (
                       SELECT 1
                       FROM pg_catalog.pg_roles AS login_role
                       WHERE login_role.rolname = session_user
                         AND login_role.rolcanlogin IS TRUE
                         AND (
                             login_role.rolsuper IS TRUE
                             OR (
                                 login_role.rolbypassrls IS FALSE
                                 AND pg_catalog.pg_has_role(
                                     session_user,
                                     '{PLATFORM_APPLICATION_ROLE}',
                                     'SET'
                                 )
                             )
                         )
                   ) THEN
                    RAISE EXCEPTION 'Initial administrator is unavailable'
                        USING ERRCODE = 'WF003';
                END IF;

                PERFORM pg_catalog.set_config(
                    'app.tenant_id', requested_tenant_id::text, true
                );
                BEGIN
                    PERFORM pg_catalog.pg_advisory_xact_lock(
                        pg_catalog.hashtextextended(requested_tenant_id::text, 11044)
                    );

                    SELECT tenants.status INTO canonical_tenant_status
                    FROM public.tenants AS tenants
                    WHERE tenants.id = requested_tenant_id;
                    IF NOT FOUND
                       OR canonical_tenant_status NOT IN (
                           'provisioning', 'trial', 'active'
                       ) THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT
                        pg_catalog.count(events.aggregate_id),
                        pg_catalog.min(events.aggregate_id::text)::uuid,
                        pg_catalog.min(events.payload ->> 'activation_id')::uuid
                    INTO
                        original_invitation_count,
                        original_user_id,
                        original_activation_id
                    FROM public.outbox_events AS events
                    WHERE events.tenant_id = requested_tenant_id
                      AND events.aggregate_type = 'identity_membership'
                      AND events.event_type = '{_INVITATION_EVENT_TYPE}'
                      AND events.source_key = '{_INVITATION_EVENT_TYPE}:'
                          || events.aggregate_id::text
                      AND pg_catalog.jsonb_typeof(events.payload) = 'object'
                      AND events.payload ? 'recipient_user_id'
                      AND events.payload ? 'activation_id'
                      AND events.payload
                          - 'recipient_user_id' - 'activation_id' = '{{}}'::jsonb
                      AND events.payload ->> 'recipient_user_id'
                          = events.aggregate_id::text
                      AND events.payload ->> 'activation_id' ~
                          '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-'
                          '[0-9a-f]{{4}}-[0-9a-f]{{12}}$';
                    IF original_invitation_count <> 1
                       OR original_user_id IS NULL
                       OR original_user_id
                           = '00000000-0000-0000-0000-000000000000'::uuid
                       OR original_activation_id IS NULL
                       OR original_activation_id
                           = '00000000-0000-0000-0000-000000000000'::uuid THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    PERFORM tokens.id
                    FROM public.user_activation_tokens AS tokens
                    WHERE tokens.tenant_id = requested_tenant_id
                      AND tokens.user_id = original_user_id
                    FOR UPDATE;
                    SELECT
                        pg_catalog.count(tokens.id) FILTER (
                            WHERE tokens.consumed_at IS NOT NULL
                        ),
                        pg_catalog.count(tokens.id) FILTER (
                            WHERE tokens.id = original_activation_id
                        )
                    INTO consumed_activation_count, original_activation_count
                    FROM public.user_activation_tokens AS tokens
                    WHERE tokens.tenant_id = requested_tenant_id
                      AND tokens.user_id = original_user_id;
                    IF consumed_activation_count <> 0
                       OR original_activation_count <> 1 THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT
                        users.status,
                        users.email_normalized,
                        users.password_hash
                    INTO
                        local_user_status,
                        local_user_email,
                        local_password_hash
                    FROM public.users AS users
                    WHERE users.tenant_id = requested_tenant_id
                      AND users.id = original_user_id
                    FOR UPDATE OF users;
                    IF NOT FOUND
                       OR local_user_status <> 'invited'
                       OR local_password_hash IS NOT NULL THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT memberships.identity_id, memberships.status
                    INTO membership_identity_id, membership_status
                    FROM public.tenant_memberships AS memberships
                    WHERE memberships.tenant_id = requested_tenant_id
                      AND memberships.id = original_user_id
                      AND memberships.legacy_user_id = original_user_id
                    FOR UPDATE OF memberships;
                    IF NOT FOUND OR membership_status <> 'invited' THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT identities.status, identities.email_normalized
                    INTO old_identity_status, old_identity_email
                    FROM public.identities AS identities
                    WHERE identities.id = membership_identity_id
                    FOR UPDATE OF identities;
                    IF NOT FOUND
                       OR old_identity_status NOT IN ('pending', 'active')
                       OR old_identity_email IS DISTINCT FROM local_user_email THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT
                        pg_catalog.count(roles.role_id),
                        pg_catalog.count(roles.role_id) FILTER (
                            WHERE roles.role_id = '{_TENANT_ADMIN_ROLE_ID}'::uuid
                              AND roles.role_scope_type = 'tenant'
                        )
                    INTO active_user_role_count, active_user_tenant_admin_count
                    FROM public.user_roles AS roles
                    WHERE roles.tenant_id = requested_tenant_id
                      AND roles.user_id = original_user_id
                      AND roles.active IS TRUE;
                    SELECT
                        pg_catalog.count(roles.role_id),
                        pg_catalog.count(roles.role_id) FILTER (
                            WHERE roles.role_id = '{_TENANT_ADMIN_ROLE_ID}'::uuid
                              AND roles.role_scope_type = 'tenant'
                        )
                    INTO
                        active_membership_role_count,
                        active_membership_tenant_admin_count
                    FROM public.membership_roles AS roles
                    WHERE roles.tenant_id = requested_tenant_id
                      AND roles.membership_id = original_user_id
                      AND roles.active IS TRUE;
                    IF active_user_role_count <> 1
                       OR active_user_tenant_admin_count <> 1
                       OR active_membership_role_count <> 1
                       OR active_membership_tenant_admin_count <> 1 THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    PERFORM pg_catalog.pg_advisory_xact_lock(
                        pg_catalog.hashtextextended(requested_email, 11044)
                    );
                    SELECT identities.id, identities.status
                    INTO target_identity_id, target_identity_status
                    FROM public.identities AS identities
                    WHERE identities.email_normalized = requested_email
                    FOR UPDATE OF identities;
                    IF FOUND AND target_identity_status NOT IN ('pending', 'active') THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    SELECT pg_catalog.count(memberships.id)
                    INTO conflicting_membership_count
                    FROM public.tenant_memberships AS memberships
                    WHERE memberships.tenant_id = requested_tenant_id
                      AND memberships.identity_id = target_identity_id
                      AND memberships.id <> original_user_id;
                    SELECT pg_catalog.count(users.id)
                    INTO duplicate_user_count
                    FROM public.users AS users
                    WHERE users.tenant_id = requested_tenant_id
                      AND users.email_normalized = requested_email
                      AND users.id <> original_user_id;
                    IF conflicting_membership_count <> 0
                       OR duplicate_user_count <> 0 THEN
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    END IF;

                    IF target_identity_id IS NULL THEN
                        IF EXISTS (
                            SELECT 1
                            FROM public.identities AS identities
                            WHERE identities.id = requested_identity_id
                        ) THEN
                            RAISE EXCEPTION 'Initial administrator is unavailable'
                                USING ERRCODE = 'WF003';
                        END IF;
                        INSERT INTO public.identities (
                            id, email, status, password_hash
                        ) VALUES (
                            requested_identity_id, requested_email, 'pending', NULL
                        );
                        target_identity_id := requested_identity_id;
                    END IF;

                    corrected_at := pg_catalog.clock_timestamp();
                    UPDATE public.users AS users
                    SET email = requested_email,
                        full_name = requested_full_name,
                        updated_at = corrected_at
                    WHERE users.tenant_id = requested_tenant_id
                      AND users.id = original_user_id;
                    UPDATE public.tenant_memberships AS memberships
                    SET identity_id = target_identity_id,
                        full_name = requested_full_name,
                        updated_at = corrected_at
                    WHERE memberships.tenant_id = requested_tenant_id
                      AND memberships.id = original_user_id
                      AND memberships.legacy_user_id = original_user_id;

                    UPDATE public.user_activation_tokens AS tokens
                    SET revoked_at = corrected_at,
                        updated_at = corrected_at
                    WHERE tokens.tenant_id = requested_tenant_id
                      AND tokens.user_id = original_user_id
                      AND tokens.consumed_at IS NULL
                      AND tokens.revoked_at IS NULL;
                    INSERT INTO public.user_activation_tokens (
                        id, tenant_id, user_id, token_hash, expires_at
                    ) VALUES (
                        requested_activation_id, requested_tenant_id,
                        original_user_id, requested_token_hash,
                        requested_expires_at
                    );
                    INSERT INTO public.outbox_events (
                        id, tenant_id, aggregate_type, aggregate_id, event_type,
                        payload, source_key, occurred_at
                    ) VALUES (
                        requested_outbox_id, requested_tenant_id,
                        'identity_membership', original_user_id,
                        '{_INVITATION_EVENT_TYPE}',
                        pg_catalog.jsonb_build_object(
                            'recipient_user_id', original_user_id::text,
                            'activation_id', requested_activation_id::text
                        ),
                        '{_INVITATION_EVENT_TYPE}:' || original_user_id::text
                            || ':correction:' || requested_activation_id::text,
                        corrected_at
                    );
                EXCEPTION
                    WHEN unique_violation THEN
                        PERFORM pg_catalog.set_config(
                            'app.tenant_id',
                            coalesce(previous_tenant_context, ''),
                            true
                        );
                        RAISE EXCEPTION 'Initial administrator is unavailable'
                            USING ERRCODE = 'WF003';
                    WHEN OTHERS THEN
                        PERFORM pg_catalog.set_config(
                            'app.tenant_id',
                            coalesce(previous_tenant_context, ''),
                            true
                        );
                        RAISE;
                END;
                PERFORM pg_catalog.set_config(
                    'app.tenant_id',
                    coalesce(previous_tenant_context, ''),
                    true
                );
            END
            $platform_initial_admin_correction$
            """
        )
    )
    _reset_gateway_acl()
    op.execute(
        sa.text(
            f"""
            DO $platform_initial_admin_owner_transfer$
            BEGIN
                EXECUTE 'GRANT CREATE ON SCHEMA public TO "{_PROJECTION_ROLE}"';
                BEGIN
                    EXECUTE 'ALTER FUNCTION {_FUNCTION_SIGNATURE} '
                            'OWNER TO "{_PROJECTION_ROLE}"';
                    EXECUTE 'ALTER FUNCTION {_REISSUE_FUNCTION_SIGNATURE} '
                            'OWNER TO "{_PROJECTION_ROLE}"';
                    EXECUTE 'ALTER FUNCTION {_CORRECTION_FUNCTION_SIGNATURE} '
                            'OWNER TO "{_PROJECTION_ROLE}"';
                EXCEPTION WHEN OTHERS THEN
                    EXECUTE 'REVOKE CREATE ON SCHEMA public FROM "{_PROJECTION_ROLE}"';
                    RAISE;
                END;
                EXECUTE 'REVOKE CREATE ON SCHEMA public FROM "{_PROJECTION_ROLE}"';
            END
            $platform_initial_admin_owner_transfer$
            """
        )
    )
    for function_signature in (
        _FUNCTION_SIGNATURE,
        _REISSUE_FUNCTION_SIGNATURE,
        _CORRECTION_FUNCTION_SIGNATURE,
    ):
        op.execute(
            sa.text(f"GRANT EXECUTE ON FUNCTION {function_signature} TO wealthy_falcon_platform")
        )


def _reset_gateway_acl() -> None:
    for function_signature in (
        _FUNCTION_SIGNATURE,
        _REISSUE_FUNCTION_SIGNATURE,
        _CORRECTION_FUNCTION_SIGNATURE,
    ):
        op.execute(sa.text(f"REVOKE ALL ON FUNCTION {function_signature} FROM PUBLIC"))
        for role_name in (
            TENANT_APPLICATION_ROLE,
            PLATFORM_APPLICATION_ROLE,
            AUTHENTICATION_APPLICATION_ROLE,
        ):
            op.execute(sa.text(f'REVOKE ALL ON FUNCTION {function_signature} FROM "{role_name}"'))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    disable_forced_row_security(op, table_name="outbox_events")
    invitation_count = int(
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM outbox_events WHERE event_type = :event_type"),
            {"event_type": _INVITATION_EVENT_TYPE},
        )
        .scalar_one()
    )
    if invitation_count:
        raise RuntimeError(
            f"0044 downgrade refused: initial_admin_invitation_events={invitation_count}"
        )
    enable_forced_row_security(op, table_name="outbox_events")

    op.execute(sa.text(f'SET LOCAL ROLE "{_PROJECTION_ROLE}"'))
    for function_signature in (
        _FUNCTION_SIGNATURE,
        _REISSUE_FUNCTION_SIGNATURE,
        _CORRECTION_FUNCTION_SIGNATURE,
    ):
        op.execute(
            sa.text(
                f"REVOKE EXECUTE ON FUNCTION {function_signature} "
                f'FROM "{PLATFORM_APPLICATION_ROLE}"'
            )
        )
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {function_signature}"))
    op.execute(sa.text("RESET ROLE"))

    grants = (
        (
            "outbox_events",
            "SELECT",
            (
                "tenant_id",
                "aggregate_type",
                "aggregate_id",
                "event_type",
                "payload",
                "source_key",
            ),
        ),
        (
            "outbox_events",
            "INSERT",
            (
                "id",
                "tenant_id",
                "aggregate_type",
                "aggregate_id",
                "event_type",
                "payload",
                "source_key",
                "occurred_at",
            ),
        ),
        (
            "user_activation_tokens",
            "UPDATE",
            ("revoked_at", "updated_at"),
        ),
        (
            "user_activation_tokens",
            "SELECT",
            ("id", "tenant_id", "user_id", "consumed_at", "revoked_at"),
        ),
        (
            "user_activation_tokens",
            "INSERT",
            (
                "id",
                "tenant_id",
                "user_id",
                "token_hash",
                "expires_at",
            ),
        ),
        (
            "user_roles",
            "INSERT",
            (
                "tenant_id",
                "user_id",
                "role_id",
                "role_scope_type",
                "active",
                "created_at",
                "updated_at",
            ),
        ),
        (
            "users",
            "UPDATE",
            (
                "email",
                "full_name",
                "updated_at",
            ),
        ),
        (
            "users",
            "INSERT",
            (
                "id",
                "tenant_id",
                "email",
                "full_name",
                "status",
                "password_hash",
                "can_invite_users",
                "permission_version",
            ),
        ),
        ("tenants", "SELECT", ("id", "status")),
    )
    for table_name, privilege, columns in grants:
        revoke_column_privilege(
            op,
            table_name=table_name,
            role_name=_PROJECTION_ROLE,
            privilege=privilege,
            column_names=columns,
        )
    for table_name, policy_name in reversed(_POLICIES):
        drop_policy(op, table_name=table_name, policy_name=policy_name)

    op.drop_constraint(_OUTBOX_CHECK, "outbox_events", type_="check")
    op.create_check_constraint(
        _OUTBOX_CHECK,
        "outbox_events",
        "event_type in "
        "('leave.requested','leave.approved','leave.rejected','leave.cancelled',"
        "'leave.balance_adjusted','announcement.published')",
    )
    _remove_notification_delivery_lifecycle()


def _remove_notification_delivery_lifecycle() -> None:
    revoke_column_privilege(
        op,
        table_name="notification_deliveries",
        role_name=TENANT_APPLICATION_ROLE,
        privilege="UPDATE",
        column_names=_DELIVERY_UPDATE_COLUMNS,
    )
    op.drop_constraint(
        _DELIVERY_PREPARED_MESSAGE_CHECK,
        "notification_deliveries",
        type_="check",
    )
    op.drop_constraint(
        _DELIVERY_LEASE_CHECK,
        "notification_deliveries",
        type_="check",
    )
    for column_name in reversed(_DELIVERY_UPDATE_COLUMNS):
        op.drop_column("notification_deliveries", column_name)


__all__ = ["revision", "down_revision", "upgrade", "downgrade"]
