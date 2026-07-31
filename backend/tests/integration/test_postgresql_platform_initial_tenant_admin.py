from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from app.platform.db import sqlstate_from_error
from app.platform.db.tenant_access import (
    AUTHENTICATION_APPLICATION_ROLE,
    PLATFORM_APPLICATION_ROLE,
    TENANT_APPLICATION_ROLE,
)
from app.platform.identity import AccessTokenCodec, PasswordManager, issue_activation_token
from app.services.authentication_service import (
    AuthenticatedUser,
    AuthenticationService,
    InvalidActivationError,
)
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.elements import TextClause

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "alembic.ini"

PRE_REVISION = "0043_p11_employee_lifecycle_profile_lock"
REVISION = "0044_platform_initial_tenant_admin"
FUNCTION_NAME = "provision_platform_initial_tenant_admin"
FUNCTION_REGPROCEDURE = (
    "public.provision_platform_initial_tenant_admin(uuid,uuid,text,text,uuid,text,timestamptz,uuid)"
)
REISSUE_FUNCTION_NAME = "reissue_platform_initial_tenant_admin_invitation"
REISSUE_FUNCTION_REGPROCEDURE = (
    "public.reissue_platform_initial_tenant_admin_invitation(uuid,uuid,text,timestamptz,uuid)"
)
CORRECTION_FUNCTION_NAME = "correct_platform_initial_tenant_admin_invitation"
CORRECTION_FUNCTION_REGPROCEDURE = (
    "public.correct_platform_initial_tenant_admin_invitation("
    "uuid,text,text,uuid,uuid,text,timestamptz,uuid)"
)
PROJECTION_ROLE = "wealthy_falcon_identity_projection"
TENANT_ADMIN_ROLE_ID = UUID("d2000000-0000-4000-8000-000000000002")
INVITATION_EVENT_TYPE = "identity.initial_admin_invited"
INITIAL_ADMIN_UNAVAILABLE_SQLSTATE = "WF003"
MIGRATION_OWNED_TABLES = (
    "alembic_version",
    "tenants",
    "users",
    "user_roles",
    "user_activation_tokens",
    "outbox_events",
    "notification_deliveries",
)

POLICY_NAMES = {
    ("tenants", "platform_initial_admin_tenant_read"),
    ("users", "platform_initial_admin_user_insert"),
    ("users", "platform_initial_admin_user_update"),
    ("user_roles", "platform_initial_admin_user_role_insert"),
    ("user_activation_tokens", "platform_initial_admin_activation_insert"),
    ("user_activation_tokens", "platform_initial_admin_activation_select"),
    ("user_activation_tokens", "platform_initial_admin_activation_update"),
    ("outbox_events", "platform_initial_admin_outbox_insert"),
    ("outbox_events", "platform_initial_admin_outbox_select"),
}
EXPECTED_COLUMN_GRANTS = {
    ("tenants", "id", "SELECT"),
    ("tenants", "status", "SELECT"),
    *(
        ("users", column_name, "INSERT")
        for column_name in (
            "id",
            "tenant_id",
            "email",
            "full_name",
            "status",
            "password_hash",
            "can_invite_users",
            "permission_version",
        )
    ),
    *(
        ("users", column_name, "UPDATE")
        for column_name in (
            "email",
            "full_name",
            "updated_at",
        )
    ),
    *(
        ("user_roles", column_name, "INSERT")
        for column_name in (
            "tenant_id",
            "user_id",
            "role_id",
            "role_scope_type",
            "active",
            "created_at",
            "updated_at",
        )
    ),
    *(
        ("user_activation_tokens", column_name, "INSERT")
        for column_name in (
            "id",
            "tenant_id",
            "user_id",
            "token_hash",
            "expires_at",
        )
    ),
    *(
        ("user_activation_tokens", column_name, "SELECT")
        for column_name in (
            "id",
            "tenant_id",
            "user_id",
            "consumed_at",
            "revoked_at",
        )
    ),
    *(
        ("user_activation_tokens", column_name, "UPDATE")
        for column_name in (
            "revoked_at",
            "updated_at",
        )
    ),
    *(
        ("outbox_events", column_name, "INSERT")
        for column_name in (
            "id",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
            "source_key",
            "occurred_at",
        )
    ),
    *(
        ("outbox_events", column_name, "SELECT")
        for column_name in (
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
            "source_key",
        )
    ),
}
GATEWAY_CALL = text(
    f"""
    select public.{FUNCTION_NAME}(
        :tenant_id,
        :user_id,
        :full_name,
        :email,
        :activation_id,
        :token_hash,
        :expires_at,
        :outbox_id
    )
    """
)
REISSUE_GATEWAY_CALL = text(
    f"""
    select public.{REISSUE_FUNCTION_NAME}(
        :tenant_id,
        :activation_id,
        :token_hash,
        :expires_at,
        :outbox_id
    )
    """
)
CORRECTION_GATEWAY_CALL = text(
    f"""
    select public.{CORRECTION_FUNCTION_NAME}(
        :tenant_id,
        :full_name,
        :email,
        :identity_id,
        :activation_id,
        :token_hash,
        :expires_at,
        :outbox_id
    )
    """
)


@pytest.fixture
def initial_admin_postgres_database(postgres_database_url: URL) -> URL:
    alembic_command.upgrade(_alembic_config(postgres_database_url), REVISION)
    return postgres_database_url


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    tenant_id: UUID
    user_id: UUID
    full_name: str
    email: str
    activation_id: UUID
    token_hash: str
    expires_at: datetime
    outbox_id: UUID
    slug: str

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "full_name": self.full_name,
            "email": self.email,
            "activation_id": self.activation_id,
            "token_hash": self.token_hash,
            "expires_at": self.expires_at,
            "outbox_id": self.outbox_id,
        }


@dataclass(frozen=True, slots=True)
class ReissueGatewayRequest:
    tenant_id: UUID
    activation_id: UUID
    token_hash: str
    expires_at: datetime
    outbox_id: UUID

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "activation_id": self.activation_id,
            "token_hash": self.token_hash,
            "expires_at": self.expires_at,
            "outbox_id": self.outbox_id,
        }


@dataclass(frozen=True, slots=True)
class CorrectionGatewayRequest:
    tenant_id: UUID
    full_name: str
    email: str
    identity_id: UUID
    activation_id: UUID
    token_hash: str
    expires_at: datetime
    outbox_id: UUID

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "full_name": self.full_name,
            "email": self.email,
            "identity_id": self.identity_id,
            "activation_id": self.activation_id,
            "token_hash": self.token_hash,
            "expires_at": self.expires_at,
            "outbox_id": self.outbox_id,
        }


def test_0044_gateway_catalog_is_security_definer_and_narrow(
    initial_admin_postgres_database: URL,
) -> None:
    asyncio.run(_assert_gateway_catalog(initial_admin_postgres_database))


def test_0044_notification_delivery_claim_schema_is_guarded_and_worker_writable(
    initial_admin_postgres_database: URL,
) -> None:
    asyncio.run(_assert_notification_delivery_claim_schema(initial_admin_postgres_database))


def test_0044_gateway_enforces_callers_credentials_roles_and_atomicity(
    initial_admin_postgres_database: URL,
) -> None:
    platform_login = f"wf_initial_admin_platform_{uuid4().hex[:16]}"
    outsider_login = f"wf_initial_admin_outsider_{uuid4().hex[:16]}"
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )
    )
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            outsider_login,
        )
    )
    platform_url = initial_admin_postgres_database.set(
        username=platform_login,
        password=None,
    )
    outsider_url = initial_admin_postgres_database.set(
        username=outsider_login,
        password=None,
    )

    try:
        outsider_request = _gateway_request(
            label="outsider",
            email="outsider.initial.admin@example.test",
        )
        with pytest.raises(DBAPIError) as outsider_error:
            asyncio.run(_call_gateway(outsider_url, outsider_request))
        assert sqlstate_from_error(outsider_error.value) == "42501"

        new_identity_request = _gateway_request(
            label="new-identity",
            email="new.initial.admin@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    new_identity_request,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        new_projection = asyncio.run(
            _tenant_projection(
                initial_admin_postgres_database,
                new_identity_request.tenant_id,
            )
        )
        assert new_projection["user"] == (
            new_identity_request.user_id,
            new_identity_request.email,
            new_identity_request.full_name,
            "invited",
            None,
            False,
            1,
        )
        assert new_projection["identity"] == (
            new_identity_request.user_id,
            new_identity_request.email,
            "pending",
            None,
            1,
        )
        assert new_projection["membership"] == (
            new_identity_request.user_id,
            new_identity_request.user_id,
            new_identity_request.full_name,
            "invited",
            1,
        )
        _assert_only_tenant_admin_role(new_projection, new_identity_request.user_id)
        _assert_activation_and_outbox(new_projection, new_identity_request)

        existing_identity_id = uuid4()
        existing_identity_email = "existing.initial.admin@example.test"
        existing_password_hash = "$argon2id$existing-credential-must-not-change"
        asyncio.run(
            _seed_identity(
                initial_admin_postgres_database,
                identity_id=existing_identity_id,
                email=existing_identity_email,
                status="active",
                password_hash=existing_password_hash,
                platform_permission_version=7,
            )
        )
        identity_before = asyncio.run(
            _identity_security_state(
                initial_admin_postgres_database,
                existing_identity_id,
            )
        )
        existing_identity_request = _gateway_request(
            label="existing-identity",
            email=existing_identity_email,
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    existing_identity_request,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        assert (
            asyncio.run(
                _identity_security_state(
                    initial_admin_postgres_database,
                    existing_identity_id,
                )
            )
            == identity_before
        )
        existing_projection = asyncio.run(
            _tenant_projection(
                initial_admin_postgres_database,
                existing_identity_request.tenant_id,
            )
        )
        assert existing_projection["user"] == (
            existing_identity_request.user_id,
            existing_identity_request.email,
            existing_identity_request.full_name,
            "invited",
            None,
            False,
            1,
        )
        assert existing_projection["identity"] == (
            existing_identity_id,
            existing_identity_email,
            "active",
            existing_password_hash,
            7,
        )
        assert existing_projection["membership"] == (
            existing_identity_request.user_id,
            existing_identity_id,
            existing_identity_request.full_name,
            "invited",
            1,
        )
        _assert_only_tenant_admin_role(
            existing_projection,
            existing_identity_request.user_id,
        )
        _assert_activation_and_outbox(
            existing_projection,
            existing_identity_request,
        )

        duplicate_request = _gateway_request(
            label="duplicate",
            email="duplicate.initial.admin@example.test",
            tenant_id=new_identity_request.tenant_id,
        )
        with pytest.raises(DBAPIError) as duplicate_error:
            asyncio.run(
                _call_gateway(
                    platform_url,
                    duplicate_request,
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(duplicate_error.value) == INITIAL_ADMIN_UNAVAILABLE_SQLSTATE
        assert (
            asyncio.run(
                _tenant_projection(
                    initial_admin_postgres_database,
                    new_identity_request.tenant_id,
                )
            )
            == new_projection
        )

        locked_identity_id = uuid4()
        locked_identity_email = "locked.initial.admin@example.test"
        locked_password_hash = "$argon2id$locked-credential-must-not-change"
        asyncio.run(
            _seed_identity(
                initial_admin_postgres_database,
                identity_id=locked_identity_id,
                email=locked_identity_email,
                status="locked",
                password_hash=locked_password_hash,
                platform_permission_version=11,
            )
        )
        locked_identity_before = asyncio.run(
            _identity_security_state(
                initial_admin_postgres_database,
                locked_identity_id,
            )
        )
        unavailable_request = _gateway_request(
            label="unavailable",
            email=locked_identity_email,
        )
        with pytest.raises(DBAPIError) as unavailable_error:
            asyncio.run(
                _call_gateway(
                    platform_url,
                    unavailable_request,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(unavailable_error.value) == INITIAL_ADMIN_UNAVAILABLE_SQLSTATE
        assert asyncio.run(
            _tenant_row_count(
                initial_admin_postgres_database,
                unavailable_request.tenant_id,
            )
        ) == (0, 0, 0, 0, 0, 0)
        assert (
            asyncio.run(
                _identity_security_state(
                    initial_admin_postgres_database,
                    locked_identity_id,
                )
            )
            == locked_identity_before
        )

        config = _alembic_config(initial_admin_postgres_database)
        with pytest.raises(
            RuntimeError,
            match="0044 downgrade refused: initial_admin_invitation_events=2",
        ):
            alembic_command.downgrade(config, PRE_REVISION)
        assert asyncio.run(_current_revision(initial_admin_postgres_database)) == REVISION
        assert asyncio.run(_gateway_exists(initial_admin_postgres_database))
        assert asyncio.run(
            _row_security_flags(
                initial_admin_postgres_database,
                "outbox_events",
            )
        ) == (True, True)
    finally:
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                outsider_login,
            )
        )
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                platform_login,
                capability_role=PLATFORM_APPLICATION_ROLE,
            )
        )


def test_0044_reissue_gateway_targets_original_rotates_and_rejects_ineligible_states(
    initial_admin_postgres_database: URL,
) -> None:
    platform_login = f"wf_reissue_platform_{uuid4().hex[:16]}"
    outsider_login = f"wf_reissue_outsider_{uuid4().hex[:16]}"
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )
    )
    asyncio.run(_create_login_role(initial_admin_postgres_database, outsider_login))
    platform_url = initial_admin_postgres_database.set(
        username=platform_login,
        password=None,
    )
    outsider_url = initial_admin_postgres_database.set(
        username=outsider_login,
        password=None,
    )

    try:
        existing_identity_id = uuid4()
        existing_identity_email = "reissue.existing.identity@example.test"
        existing_password_hash = "$argon2id$reissue-existing-credential-must-not-change"
        asyncio.run(
            _seed_identity(
                initial_admin_postgres_database,
                identity_id=existing_identity_id,
                email=existing_identity_email,
                status="active",
                password_hash=existing_password_hash,
                platform_permission_version=13,
            )
        )
        identity_before = asyncio.run(
            _identity_security_state(
                initial_admin_postgres_database,
                existing_identity_id,
            )
        )
        original = _gateway_request(
            label="reissue-original",
            email=existing_identity_email,
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    original,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        decoy_user_id = asyncio.run(
            _seed_decoy_invited_tenant_admin(
                initial_admin_postgres_database,
                tenant_id=original.tenant_id,
                label="reissue-decoy",
            )
        )
        before_reissue = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                original.tenant_id,
            )
        )
        reissue = _reissue_gateway_request(original.tenant_id)

        with pytest.raises(DBAPIError) as outsider_error:
            asyncio.run(_call_reissue_gateway(outsider_url, reissue))
        assert sqlstate_from_error(outsider_error.value) == "42501"
        assert (
            asyncio.run(
                _invitation_history(
                    initial_admin_postgres_database,
                    original.tenant_id,
                )
            )
            == before_reissue
        )

        assert (
            asyncio.run(
                _call_reissue_gateway(
                    platform_url,
                    reissue,
                    assume_platform_role=True,
                )
            )
            is None
        )
        after_reissue = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                original.tenant_id,
            )
        )
        _assert_stable_invitation_principals(before_reissue, after_reissue)
        assert (
            asyncio.run(
                _identity_security_state(
                    initial_admin_postgres_database,
                    existing_identity_id,
                )
            )
            == identity_before
        )
        _assert_reissue_history(
            after_reissue,
            original=original,
            reissues=(reissue,),
            expected_live_ids={reissue.activation_id},
        )
        assert all(
            activation["user_id"] != decoy_user_id for activation in after_reissue["activations"]
        )
        assert all(
            outbox["aggregate_id"] != decoy_user_id for outbox in after_reissue["outbox_events"]
        )

        activated = _gateway_request(
            label="reissue-activated",
            email="reissue.activated@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    activated,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        asyncio.run(
            _mark_initial_admin_activated(
                initial_admin_postgres_database,
                activated,
            )
        )
        activated_before = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                activated.tenant_id,
            )
        )
        with pytest.raises(DBAPIError) as activated_error:
            asyncio.run(
                _call_reissue_gateway(
                    platform_url,
                    _reissue_gateway_request(activated.tenant_id),
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(activated_error.value) == (INITIAL_ADMIN_UNAVAILABLE_SQLSTATE)
        assert (
            asyncio.run(
                _invitation_history(
                    initial_admin_postgres_database,
                    activated.tenant_id,
                )
            )
            == activated_before
        )

        active_membership = _gateway_request(
            label="reissue-active-membership",
            email="reissue.active.membership@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    active_membership,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        asyncio.run(
            _set_initial_admin_membership_status(
                initial_admin_postgres_database,
                active_membership,
                status="active",
            )
        )
        active_membership_before = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                active_membership.tenant_id,
            )
        )
        with pytest.raises(DBAPIError) as active_membership_error:
            asyncio.run(
                _call_reissue_gateway(
                    platform_url,
                    _reissue_gateway_request(active_membership.tenant_id),
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(active_membership_error.value) == (
            INITIAL_ADMIN_UNAVAILABLE_SQLSTATE
        )
        assert (
            asyncio.run(
                _invitation_history(
                    initial_admin_postgres_database,
                    active_membership.tenant_id,
                )
            )
            == active_membership_before
        )

        arbitrary = _gateway_request(
            label="reissue-arbitrary",
            email="reissue.arbitrary@example.test",
        )
        asyncio.run(
            _insert_tenant_without_initial_admin(
                initial_admin_postgres_database,
                arbitrary,
            )
        )
        asyncio.run(
            _seed_decoy_invited_tenant_admin(
                initial_admin_postgres_database,
                tenant_id=arbitrary.tenant_id,
                label="reissue-arbitrary",
            )
        )
        arbitrary_before = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                arbitrary.tenant_id,
            )
        )
        with pytest.raises(DBAPIError) as arbitrary_error:
            asyncio.run(
                _call_reissue_gateway(
                    platform_url,
                    _reissue_gateway_request(arbitrary.tenant_id),
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(arbitrary_error.value) == (INITIAL_ADMIN_UNAVAILABLE_SQLSTATE)
        assert (
            asyncio.run(
                _invitation_history(
                    initial_admin_postgres_database,
                    arbitrary.tenant_id,
                )
            )
            == arbitrary_before
        )
    finally:
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                outsider_login,
            )
        )
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                platform_login,
                capability_role=PLATFORM_APPLICATION_ROLE,
            )
        )


def test_0044_concurrent_reissues_leave_one_live_token_and_distinct_events(
    initial_admin_postgres_database: URL,
) -> None:
    platform_login = f"wf_reissue_race_{uuid4().hex[:16]}"
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )
    )
    platform_url = initial_admin_postgres_database.set(
        username=platform_login,
        password=None,
    )

    try:
        original = _gateway_request(
            label="reissue-race",
            email="reissue.race@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    original,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        identity_before = asyncio.run(
            _identity_security_state(
                initial_admin_postgres_database,
                original.user_id,
            )
        )
        before_reissues = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                original.tenant_id,
            )
        )
        reissues = (
            _reissue_gateway_request(original.tenant_id),
            _reissue_gateway_request(original.tenant_id),
        )

        assert asyncio.run(
            _call_reissue_gateways_concurrently(
                platform_url,
                reissues,
            )
        ) == (None, None)

        after_reissues = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                original.tenant_id,
            )
        )
        _assert_stable_invitation_principals(before_reissues, after_reissues)
        assert (
            asyncio.run(
                _identity_security_state(
                    initial_admin_postgres_database,
                    original.user_id,
                )
            )
            == identity_before
        )
        live_ids = {
            activation["id"]
            for activation in after_reissues["activations"]
            if activation["consumed_at"] is None and activation["revoked_at"] is None
        }
        assert live_ids <= {request.activation_id for request in reissues}
        assert len(live_ids) == 1
        _assert_reissue_history(
            after_reissues,
            original=original,
            reissues=reissues,
            expected_live_ids=live_ids,
        )
    finally:
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                platform_login,
                capability_role=PLATFORM_APPLICATION_ROLE,
            )
        )


def test_0044_correction_reassociates_only_original_unactivated_membership_atomically(
    initial_admin_postgres_database: URL,
) -> None:
    platform_login = f"wf_correction_platform_{uuid4().hex[:16]}"
    outsider_login = f"wf_correction_outsider_{uuid4().hex[:16]}"
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )
    )
    asyncio.run(_create_login_role(initial_admin_postgres_database, outsider_login))
    platform_url = initial_admin_postgres_database.set(
        username=platform_login,
        password=None,
    )
    outsider_url = initial_admin_postgres_database.set(
        username=outsider_login,
        password=None,
    )

    old_identity_id = uuid4()
    target_identity_id = uuid4()
    old_email = f"correction.old.{uuid4().hex[:12]}@example.test"
    target_email = f"correction.target.{uuid4().hex[:12]}@example.test"
    old_hash = "$argon2id$correction-old-global-credential-must-not-change"
    target_hash = "$argon2id$correction-target-global-credential-must-not-change"
    try:
        asyncio.run(
            _seed_identity(
                initial_admin_postgres_database,
                identity_id=old_identity_id,
                email=old_email,
                status="active",
                password_hash=old_hash,
                platform_permission_version=7,
            )
        )
        other_membership = _gateway_request(
            label="correction-other-membership",
            email=old_email,
        )
        subject = _gateway_request(
            label="correction-subject",
            email=old_email,
        )
        for request in (other_membership, subject):
            assert (
                asyncio.run(
                    _call_gateway(
                        platform_url,
                        request,
                        insert_tenant=True,
                        assume_platform_role=True,
                    )
                )
                is None
            )
        asyncio.run(
            _seed_identity(
                initial_admin_postgres_database,
                identity_id=target_identity_id,
                email=target_email,
                status="active",
                password_hash=target_hash,
                platform_permission_version=13,
            )
        )
        old_identity_before = asyncio.run(
            _identity_security_state(initial_admin_postgres_database, old_identity_id)
        )
        target_identity_before = asyncio.run(
            _identity_security_state(initial_admin_postgres_database, target_identity_id)
        )
        other_membership_before = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                other_membership.tenant_id,
            )
        )
        subject_before = asyncio.run(
            _invitation_history(initial_admin_postgres_database, subject.tenant_id)
        )
        correction = _correction_gateway_request(
            subject.tenant_id,
            full_name="Corrected Initial Admin",
            email=target_email,
        )

        with pytest.raises(DBAPIError) as unauthorized:
            asyncio.run(
                _call_correction_gateway(
                    outsider_url,
                    correction,
                )
            )
        assert sqlstate_from_error(unauthorized.value) == "42501"
        assert (
            asyncio.run(_invitation_history(initial_admin_postgres_database, subject.tenant_id))
            == subject_before
        )

        assert (
            asyncio.run(
                _call_correction_gateway(
                    platform_url,
                    correction,
                    assume_platform_role=True,
                )
            )
            is None
        )

        corrected = asyncio.run(
            _invitation_history(initial_admin_postgres_database, subject.tenant_id)
        )
        assert (
            asyncio.run(_identity_security_state(initial_admin_postgres_database, old_identity_id))
            == old_identity_before
        )
        assert (
            asyncio.run(
                _identity_security_state(initial_admin_postgres_database, target_identity_id)
            )
            == target_identity_before
        )
        assert (
            asyncio.run(
                _invitation_history(
                    initial_admin_postgres_database,
                    other_membership.tenant_id,
                )
            )
            == other_membership_before
        )
        assert len(corrected["users"]) == 1
        assert corrected["users"][0]["id"] == subject.user_id
        assert corrected["users"][0]["email"] == target_email
        assert corrected["users"][0]["full_name"] == "Corrected Initial Admin"
        assert corrected["users"][0]["status"] == "invited"
        assert corrected["users"][0]["password_hash"] is None
        assert len(corrected["memberships"]) == 1
        assert corrected["memberships"][0]["id"] == subject.user_id
        assert corrected["memberships"][0]["legacy_user_id"] == subject.user_id
        assert corrected["memberships"][0]["identity_id"] == target_identity_id
        assert corrected["memberships"][0]["full_name"] == "Corrected Initial Admin"
        assert corrected["user_roles"] == subject_before["user_roles"]
        assert corrected["membership_roles"] == subject_before["membership_roles"]

        activations = {activation["id"]: activation for activation in corrected["activations"]}
        assert set(activations) == {subject.activation_id, correction.activation_id}
        assert activations[subject.activation_id]["revoked_at"] is not None
        assert activations[correction.activation_id]["revoked_at"] is None
        assert all(activation["consumed_at"] is None for activation in activations.values())
        events = {event["id"]: event for event in corrected["outbox_events"]}
        assert set(events) == {subject.outbox_id, correction.outbox_id}
        assert events[correction.outbox_id]["aggregate_id"] == subject.user_id
        assert events[correction.outbox_id]["payload"] == {
            "recipient_user_id": str(subject.user_id),
            "activation_id": str(correction.activation_id),
        }
        assert events[correction.outbox_id]["source_key"] == (
            f"{INVITATION_EVENT_TYPE}:{subject.user_id}:correction:{correction.activation_id}"
        )
        assert (
            asyncio.run(
                _identity_exists(
                    initial_admin_postgres_database,
                    correction.identity_id,
                )
            )
            is False
        )
    finally:
        asyncio.run(_drop_login_role(initial_admin_postgres_database, outsider_login))
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                platform_login,
                capability_role=PLATFORM_APPLICATION_ROLE,
            )
        )


def test_0044_correction_rejects_duplicate_target_and_activated_state_without_partial_writes(
    initial_admin_postgres_database: URL,
) -> None:
    platform_login = f"wf_correction_conflict_{uuid4().hex[:16]}"
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )
    )
    platform_url = initial_admin_postgres_database.set(
        username=platform_login,
        password=None,
    )
    try:
        duplicate_subject = _gateway_request(
            label="correction-duplicate",
            email=f"correction.duplicate.original.{uuid4().hex[:10]}@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    duplicate_subject,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        target_identity_id = uuid4()
        target_user_id = uuid4()
        target_email = f"correction.duplicate.target.{uuid4().hex[:10]}@example.test"
        target_hash = "$argon2id$duplicate-target-credential-must-not-change"
        asyncio.run(
            _seed_identity(
                initial_admin_postgres_database,
                identity_id=target_identity_id,
                email=target_email,
                status="active",
                password_hash=target_hash,
                platform_permission_version=5,
            )
        )
        asyncio.run(
            _seed_identity_tenant_membership(
                initial_admin_postgres_database,
                tenant_id=duplicate_subject.tenant_id,
                identity_id=target_identity_id,
                user_id=target_user_id,
                email=target_email,
                password_hash=target_hash,
            )
        )
        duplicate_before = asyncio.run(
            _invitation_history(
                initial_admin_postgres_database,
                duplicate_subject.tenant_id,
            )
        )
        target_before = asyncio.run(
            _identity_security_state(initial_admin_postgres_database, target_identity_id)
        )
        with pytest.raises(DBAPIError) as duplicate_error:
            asyncio.run(
                _call_correction_gateway(
                    platform_url,
                    _correction_gateway_request(
                        duplicate_subject.tenant_id,
                        full_name="Must Not Apply",
                        email=target_email,
                    ),
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(duplicate_error.value) == INITIAL_ADMIN_UNAVAILABLE_SQLSTATE
        assert (
            asyncio.run(
                _invitation_history(
                    initial_admin_postgres_database,
                    duplicate_subject.tenant_id,
                )
            )
            == duplicate_before
        )
        assert (
            asyncio.run(
                _identity_security_state(initial_admin_postgres_database, target_identity_id)
            )
            == target_before
        )

        activated = _gateway_request(
            label="correction-activated",
            email=f"correction.activated.{uuid4().hex[:12]}@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    activated,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        asyncio.run(
            _mark_initial_admin_activated(
                initial_admin_postgres_database,
                activated,
            )
        )
        activated_before = asyncio.run(
            _invitation_history(initial_admin_postgres_database, activated.tenant_id)
        )
        with pytest.raises(DBAPIError) as activated_error:
            asyncio.run(
                _call_correction_gateway(
                    platform_url,
                    _correction_gateway_request(
                        activated.tenant_id,
                        full_name="Must Not Reactivate",
                        email=f"must.not.apply.{uuid4().hex[:12]}@example.test",
                    ),
                    assume_platform_role=True,
                )
            )
        assert sqlstate_from_error(activated_error.value) == INITIAL_ADMIN_UNAVAILABLE_SQLSTATE
        assert (
            asyncio.run(_invitation_history(initial_admin_postgres_database, activated.tenant_id))
            == activated_before
        )
    finally:
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                platform_login,
                capability_role=PLATFORM_APPLICATION_ROLE,
            )
        )


def test_0044_concurrent_correction_and_reissue_serialize_to_one_live_invitation(
    initial_admin_postgres_database: URL,
) -> None:
    platform_login = f"wf_correction_reissue_{uuid4().hex[:16]}"
    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )
    )
    platform_url = initial_admin_postgres_database.set(
        username=platform_login,
        password=None,
    )
    try:
        original = _gateway_request(
            label="correction-reissue-race",
            email=f"correction.reissue.original.{uuid4().hex[:10]}@example.test",
        )
        assert (
            asyncio.run(
                _call_gateway(
                    platform_url,
                    original,
                    insert_tenant=True,
                    assume_platform_role=True,
                )
            )
            is None
        )
        old_identity_before = asyncio.run(
            _identity_security_state(initial_admin_postgres_database, original.user_id)
        )
        correction = _correction_gateway_request(
            original.tenant_id,
            full_name="Correction Reissue Winner",
            email=f"correction.reissue.target.{uuid4().hex[:10]}@example.test",
        )
        reissue = _reissue_gateway_request(original.tenant_id)

        assert asyncio.run(
            _call_correction_and_reissue_concurrently(
                platform_url,
                correction=correction,
                reissue=reissue,
            )
        ) == (None, None)

        history = asyncio.run(
            _invitation_history(initial_admin_postgres_database, original.tenant_id)
        )
        assert history["users"][0]["email"] == correction.email
        assert history["users"][0]["full_name"] == correction.full_name
        assert history["memberships"][0]["identity_id"] == correction.identity_id
        assert (
            asyncio.run(_identity_security_state(initial_admin_postgres_database, original.user_id))
            == old_identity_before
        )
        activations = {activation["id"]: activation for activation in history["activations"]}
        assert set(activations) == {
            original.activation_id,
            correction.activation_id,
            reissue.activation_id,
        }
        assert all(activation["consumed_at"] is None for activation in activations.values())
        assert sum(activation["revoked_at"] is None for activation in activations.values()) == 1
        events = {event["id"]: event for event in history["outbox_events"]}
        assert set(events) == {original.outbox_id, correction.outbox_id, reissue.outbox_id}
        assert len({event["source_key"] for event in events.values()}) == 3
        assert events[correction.outbox_id]["source_key"].endswith(
            f":correction:{correction.activation_id}"
        )
        assert events[reissue.outbox_id]["source_key"].endswith(f":reissue:{reissue.activation_id}")
    finally:
        asyncio.run(
            _drop_login_role(
                initial_admin_postgres_database,
                platform_login,
                capability_role=PLATFORM_APPLICATION_ROLE,
            )
        )


def test_0044_concurrent_correction_and_activation_have_exactly_one_winner(
    initial_admin_postgres_database: URL,
) -> None:
    asyncio.run(_assert_concurrent_correction_and_activation(initial_admin_postgres_database))


def test_0044_clean_downgrade_works_for_set_only_noinherit_migration_owner(
    initial_admin_postgres_database: URL,
) -> None:
    migration_role = f"wf_0044_set_owner_{uuid4().hex[:16]}"
    replacement_owner = initial_admin_postgres_database.username
    assert replacement_owner

    asyncio.run(
        _create_login_role(
            initial_admin_postgres_database,
            migration_role,
            capability_role=PROJECTION_ROLE,
        )
    )
    try:
        asyncio.run(
            _prepare_0044_migration_owner(
                initial_admin_postgres_database,
                migration_role,
            )
        )
        assert asyncio.run(
            _set_only_role_state(
                initial_admin_postgres_database,
                migration_role,
            )
        ) == (
            True,
            False,
            False,
            False,
            False,
            False,
            False,
            True,
            False,
        )

        migration_url = initial_admin_postgres_database.set(
            username=migration_role,
            password=None,
        )
        alembic_command.downgrade(
            _alembic_config(migration_url),
            PRE_REVISION,
        )

        assert asyncio.run(_current_revision(initial_admin_postgres_database)) == PRE_REVISION
        assert not asyncio.run(
            _function_exists(
                initial_admin_postgres_database,
                FUNCTION_REGPROCEDURE,
            )
        )
        assert not asyncio.run(
            _function_exists(
                initial_admin_postgres_database,
                REISSUE_FUNCTION_REGPROCEDURE,
            )
        )
        assert asyncio.run(_initial_admin_policy_count(initial_admin_postgres_database)) == 0
        assert asyncio.run(_projection_column_grants(initial_admin_postgres_database)) == set()
        assert INVITATION_EVENT_TYPE not in asyncio.run(
            _outbox_event_constraint(initial_admin_postgres_database)
        )
    finally:
        if asyncio.run(_current_revision(initial_admin_postgres_database)) == REVISION:
            alembic_command.downgrade(
                _alembic_config(initial_admin_postgres_database),
                PRE_REVISION,
            )
        asyncio.run(
            _remove_0044_migration_owner(
                initial_admin_postgres_database,
                migration_role,
                replacement_owner=replacement_owner,
            )
        )


def test_0044_clean_downgrade_and_reupgrade_restore_the_exact_boundary(
    initial_admin_postgres_database: URL,
) -> None:
    config = _alembic_config(initial_admin_postgres_database)

    alembic_command.downgrade(config, PRE_REVISION)
    assert asyncio.run(_current_revision(initial_admin_postgres_database)) == PRE_REVISION
    assert not asyncio.run(_gateway_exists(initial_admin_postgres_database))
    assert not asyncio.run(
        _function_exists(
            initial_admin_postgres_database,
            REISSUE_FUNCTION_REGPROCEDURE,
        )
    )
    assert not asyncio.run(
        _function_exists(
            initial_admin_postgres_database,
            CORRECTION_FUNCTION_REGPROCEDURE,
        )
    )
    assert asyncio.run(_initial_admin_policy_count(initial_admin_postgres_database)) == 0
    assert asyncio.run(_projection_column_grants(initial_admin_postgres_database)) == set()
    assert INVITATION_EVENT_TYPE not in asyncio.run(
        _outbox_event_constraint(initial_admin_postgres_database)
    )

    alembic_command.upgrade(config, REVISION)
    assert asyncio.run(_current_revision(initial_admin_postgres_database)) == REVISION
    assert asyncio.run(_gateway_exists(initial_admin_postgres_database))
    assert asyncio.run(
        _function_exists(
            initial_admin_postgres_database,
            REISSUE_FUNCTION_REGPROCEDURE,
        )
    )
    assert asyncio.run(
        _function_exists(
            initial_admin_postgres_database,
            CORRECTION_FUNCTION_REGPROCEDURE,
        )
    )
    assert asyncio.run(_initial_admin_policy_count(initial_admin_postgres_database)) == len(
        POLICY_NAMES
    )
    assert (
        asyncio.run(_projection_column_grants(initial_admin_postgres_database))
        == EXPECTED_COLUMN_GRANTS
    )
    assert INVITATION_EVENT_TYPE in asyncio.run(
        _outbox_event_constraint(initial_admin_postgres_database)
    )


async def _assert_concurrent_correction_and_activation(database_url: URL) -> None:
    platform_login = f"wf_correction_activation_{uuid4().hex[:16]}"
    await _create_login_role(
        database_url,
        platform_login,
        capability_role=PLATFORM_APPLICATION_ROLE,
    )
    platform_url = database_url.set(username=platform_login, password=None)
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    activation = issue_activation_token(uuid4())
    original = GatewayRequest(
        tenant_id=activation.tenant_id,
        user_id=uuid4(),
        full_name="Correction Activation Original",
        email=f"correction.activation.original.{uuid4().hex[:10]}@example.test",
        activation_id=uuid4(),
        token_hash=activation.token_hash,
        expires_at=datetime.now(UTC) + timedelta(hours=48),
        outbox_id=uuid4(),
        slug=f"correction-activation-{uuid4().hex[:12]}",
    )
    correction = _correction_gateway_request(
        original.tenant_id,
        full_name="Correction Activation Corrected",
        email=f"correction.activation.target.{uuid4().hex[:10]}@example.test",
    )
    service = AuthenticationService(
        session_factory=session_factory,
        password_manager=PasswordManager(),
        access_tokens=AccessTokenCodec(
            b"0044-correction-activation-signing-key",
            ttl=timedelta(minutes=5),
        ),
    )
    try:
        assert (
            await _call_gateway(
                platform_url,
                original,
                insert_tenant=True,
                assume_platform_role=True,
            )
            is None
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update public.tenants set status = 'trial', updated_at = :now "
                    "where id = :tenant_id"
                ),
                {
                    "tenant_id": original.tenant_id,
                    "now": datetime.now(UTC),
                },
            )
        original_identity_before = await _identity_security_state(
            database_url,
            original.user_id,
        )
        start = asyncio.Event()

        async def correct() -> object | None:
            await start.wait()
            return await _call_correction_gateway(
                platform_url,
                correction,
                assume_platform_role=True,
            )

        async def activate() -> AuthenticatedUser:
            await start.wait()
            return await service.activate(
                raw_token=activation.raw_token,
                password="Correction activation test password",
            )

        tasks = (asyncio.create_task(correct()), asyncio.create_task(activate()))
        start.set()
        correction_outcome, activation_outcome = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=30,
        )
        correction_won = correction_outcome is None
        activation_won = isinstance(activation_outcome, AuthenticatedUser)
        assert correction_won is not activation_won

        history = await _invitation_history(database_url, original.tenant_id)
        if correction_won:
            assert isinstance(activation_outcome, InvalidActivationError)
            assert history["users"][0]["status"] == "invited"
            assert history["users"][0]["password_hash"] is None
            assert history["users"][0]["email"] == correction.email
            assert history["memberships"][0]["status"] == "invited"
            assert history["memberships"][0]["identity_id"] == correction.identity_id
            assert len(history["activations"]) == 2
            assert (
                sum(
                    row["revoked_at"] is None and row["consumed_at"] is None
                    for row in history["activations"]
                )
                == 1
            )
            assert len(history["outbox_events"]) == 2
            assert any(
                event["source_key"].endswith(f":correction:{correction.activation_id}")
                for event in history["outbox_events"]
            )
            assert (
                await _identity_security_state(
                    database_url,
                    original.user_id,
                )
                == original_identity_before
            )
        else:
            assert isinstance(correction_outcome, DBAPIError)
            assert sqlstate_from_error(correction_outcome) == INITIAL_ADMIN_UNAVAILABLE_SQLSTATE
            assert isinstance(activation_outcome, AuthenticatedUser)
            assert history["users"][0]["status"] == "active"
            assert history["users"][0]["password_hash"] is not None
            assert history["users"][0]["email"] == original.email
            assert history["memberships"][0]["status"] == "active"
            assert history["memberships"][0]["identity_id"] == original.user_id
            assert len(history["activations"]) == 1
            assert history["activations"][0]["consumed_at"] is not None
            assert history["activations"][0]["revoked_at"] is None
            assert len(history["outbox_events"]) == 1
            assert await _identity_exists(database_url, correction.identity_id) is False
    finally:
        await engine.dispose()
        await _drop_login_role(
            database_url,
            platform_login,
            capability_role=PLATFORM_APPLICATION_ROLE,
        )


def _alembic_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def _gateway_request(
    *,
    label: str,
    email: str,
    tenant_id: UUID | None = None,
) -> GatewayRequest:
    requested_tenant_id = tenant_id or uuid4()
    raw_token = f"v1.{requested_tenant_id}.{uuid4().hex}{uuid4().hex}"
    return GatewayRequest(
        tenant_id=requested_tenant_id,
        user_id=uuid4(),
        full_name=f"{label.replace('-', ' ').title()} Admin",
        email=email,
        activation_id=uuid4(),
        token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(hours=48),
        outbox_id=uuid4(),
        slug=f"{label}-{uuid4().hex[:12]}",
    )


def _reissue_gateway_request(tenant_id: UUID) -> ReissueGatewayRequest:
    raw_token = f"v1.{tenant_id}.{uuid4().hex}{uuid4().hex}"
    return ReissueGatewayRequest(
        tenant_id=tenant_id,
        activation_id=uuid4(),
        token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(hours=48),
        outbox_id=uuid4(),
    )


def _correction_gateway_request(
    tenant_id: UUID,
    *,
    full_name: str,
    email: str,
) -> CorrectionGatewayRequest:
    raw_token = f"v1.{tenant_id}.{uuid4().hex}{uuid4().hex}"
    return CorrectionGatewayRequest(
        tenant_id=tenant_id,
        full_name=full_name,
        email=email,
        identity_id=uuid4(),
        activation_id=uuid4(),
        token_hash=sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(hours=48),
        outbox_id=uuid4(),
    )


async def _assert_notification_delivery_claim_schema(database_url: URL) -> None:
    expected_columns = {
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
    }
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            columns = set(
                await connection.scalars(
                    text(
                        "select column_name from information_schema.columns "
                        "where table_schema = 'public' "
                        "and table_name = 'notification_deliveries' "
                        "and column_name = any(:column_names)"
                    ),
                    {"column_names": sorted(expected_columns)},
                )
            )
            assert columns == expected_columns

            constraints = {
                row["conname"]: row["definition"]
                for row in (
                    await connection.execute(
                        text(
                            "select constraint_record.conname, "
                            "pg_catalog.pg_get_constraintdef("
                            "constraint_record.oid, true"
                            ") as definition "
                            "from pg_catalog.pg_constraint as constraint_record "
                            "where constraint_record.conrelid = "
                            "'public.notification_deliveries'::regclass "
                            "and constraint_record.conname in ("
                            "'ck_notification_deliveries_lease', "
                            "'ck_notification_deliveries_prepared_message'"
                            ")"
                        )
                    )
                ).mappings()
            }
            assert set(constraints) == {
                "ck_notification_deliveries_lease",
                "ck_notification_deliveries_prepared_message",
            }
            assert (
                "lease_attempt = attempt_count" in constraints["ck_notification_deliveries_lease"]
            )
            assert "channel" in constraints["ck_notification_deliveries_prepared_message"]

            for column_name in expected_columns:
                assert await connection.scalar(
                    text(
                        "select pg_catalog.has_column_privilege("
                        ":role_name, 'public.notification_deliveries', "
                        ":column_name, 'UPDATE')"
                    ),
                    {
                        "role_name": TENANT_APPLICATION_ROLE,
                        "column_name": column_name,
                    },
                )
                for role_name in (
                    PLATFORM_APPLICATION_ROLE,
                    AUTHENTICATION_APPLICATION_ROLE,
                ):
                    assert not await connection.scalar(
                        text(
                            "select pg_catalog.has_column_privilege("
                            ":role_name, 'public.notification_deliveries', "
                            ":column_name, 'UPDATE')"
                        ),
                        {
                            "role_name": role_name,
                            "column_name": column_name,
                        },
                    )
    finally:
        await engine.dispose()


async def _assert_gateway_catalog(database_url: URL) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            for signature in (
                FUNCTION_REGPROCEDURE,
                REISSUE_FUNCTION_REGPROCEDURE,
                CORRECTION_FUNCTION_REGPROCEDURE,
            ):
                function = (
                    (
                        await connection.execute(
                            text(
                                "select pg_catalog.pg_get_userbyid(procedure.proowner) as owner, "
                                "procedure.prosecdef, procedure.provolatile::text as provolatile, "
                                "pg_catalog.format_type("
                                "procedure.prorettype, NULL"
                                ") as return_type, "
                                "procedure.proconfig "
                                "from pg_catalog.pg_proc as procedure "
                                "where procedure.oid = pg_catalog.to_regprocedure(:signature)"
                            ),
                            {"signature": signature},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert function["owner"] == PROJECTION_ROLE
                assert function["prosecdef"] is True
                assert function["provolatile"] == "v"
                assert function["return_type"] == "void"
                assert tuple(function["proconfig"]) == ("search_path=pg_catalog, public",)

            role = (
                await connection.execute(
                    text(
                        "select rolcanlogin, rolsuper, rolbypassrls, rolinherit, "
                        "rolcreatedb, rolcreaterole, rolreplication "
                        "from pg_catalog.pg_roles where rolname = :role_name"
                    ),
                    {"role_name": PROJECTION_ROLE},
                )
            ).one()
            assert tuple(bool(value) for value in role) == (
                False,
                False,
                False,
                False,
                False,
                False,
                False,
            )
            assert not await connection.scalar(
                text("select pg_catalog.has_schema_privilege(:role_name, 'public', 'CREATE')"),
                {"role_name": PROJECTION_ROLE},
            )

            for signature in (
                FUNCTION_REGPROCEDURE,
                REISSUE_FUNCTION_REGPROCEDURE,
                CORRECTION_FUNCTION_REGPROCEDURE,
            ):
                direct_execute_grantees = set(
                    await connection.scalars(
                        text(
                            "select coalesce(grantee.rolname, 'PUBLIC') "
                            "from pg_catalog.pg_proc as procedure "
                            "cross join lateral pg_catalog.aclexplode(procedure.proacl) "
                            "as privilege "
                            "left join pg_catalog.pg_roles as grantee "
                            "on grantee.oid = privilege.grantee "
                            "where procedure.oid = pg_catalog.to_regprocedure(:signature) "
                            "and privilege.privilege_type = 'EXECUTE'"
                        ),
                        {"signature": signature},
                    )
                )
                assert direct_execute_grantees == {
                    PROJECTION_ROLE,
                    PLATFORM_APPLICATION_ROLE,
                }
                execute_access = {
                    role_name: bool(
                        await connection.scalar(
                            text(
                                "select pg_catalog.has_function_privilege("
                                ":role_name, :signature, 'EXECUTE')"
                            ),
                            {
                                "role_name": role_name,
                                "signature": signature,
                            },
                        )
                    )
                    for role_name in (
                        TENANT_APPLICATION_ROLE,
                        PLATFORM_APPLICATION_ROLE,
                        AUTHENTICATION_APPLICATION_ROLE,
                        PROJECTION_ROLE,
                    )
                }
                assert execute_access == {
                    TENANT_APPLICATION_ROLE: False,
                    PLATFORM_APPLICATION_ROLE: True,
                    AUTHENTICATION_APPLICATION_ROLE: False,
                    PROJECTION_ROLE: True,
                }

            policies = {
                (row["tablename"], row["policyname"]): row
                for row in (
                    await connection.execute(
                        text(
                            "select tablename, policyname, roles, cmd, qual, with_check "
                            "from pg_catalog.pg_policies "
                            "where schemaname = 'public' "
                            "and policyname like 'platform_initial_admin_%'"
                        )
                    )
                ).mappings()
            }
            assert set(policies) == POLICY_NAMES
            assert all(tuple(policy["roles"]) == (PROJECTION_ROLE,) for policy in policies.values())
            expected_policy_commands = {
                ("tenants", "platform_initial_admin_tenant_read"): "SELECT",
                ("users", "platform_initial_admin_user_insert"): "INSERT",
                ("users", "platform_initial_admin_user_update"): "UPDATE",
                ("user_roles", "platform_initial_admin_user_role_insert"): "INSERT",
                (
                    "user_activation_tokens",
                    "platform_initial_admin_activation_insert",
                ): "INSERT",
                (
                    "user_activation_tokens",
                    "platform_initial_admin_activation_select",
                ): "SELECT",
                (
                    "user_activation_tokens",
                    "platform_initial_admin_activation_update",
                ): "UPDATE",
                ("outbox_events", "platform_initial_admin_outbox_insert"): "INSERT",
                ("outbox_events", "platform_initial_admin_outbox_select"): "SELECT",
            }
            assert {
                key: policy["cmd"] for key, policy in policies.items()
            } == expected_policy_commands
            for key, command in expected_policy_commands.items():
                if command == "INSERT":
                    assert policies[key]["qual"] is None
                    assert policies[key]["with_check"]
                elif command == "SELECT":
                    assert policies[key]["qual"]
                    assert policies[key]["with_check"] is None
                else:
                    assert command == "UPDATE"
                    assert policies[key]["qual"]
                    assert policies[key]["with_check"]

            user_check = policies[("users", "platform_initial_admin_user_insert")]["with_check"]
            assert all(
                fragment in user_check
                for fragment in (
                    "(status)::text = 'invited'::text",
                    "password_hash IS NULL",
                    "can_invite_users IS FALSE",
                    "permission_version = 1",
                    "app.tenant_id",
                )
            )
            user_update = policies[("users", "platform_initial_admin_user_update")]
            assert all(
                fragment in (user_update["qual"] + user_update["with_check"])
                for fragment in (
                    "(status)::text = 'invited'::text",
                    "password_hash IS NULL",
                    "app.tenant_id",
                )
            )
            role_check = policies[("user_roles", "platform_initial_admin_user_role_insert")][
                "with_check"
            ]
            assert str(TENANT_ADMIN_ROLE_ID) in role_check
            assert "(role_scope_type)::text = 'tenant'::text" in role_check
            assert "active IS TRUE" in role_check
            outbox_check = policies[("outbox_events", "platform_initial_admin_outbox_insert")][
                "with_check"
            ]
            assert all(
                fragment in outbox_check
                for fragment in (
                    "identity_membership",
                    INVITATION_EVENT_TYPE,
                    "recipient_user_id",
                    "activation_id",
                    "payload - 'recipient_user_id'::text",
                    "- 'activation_id'::text",
                    "= '{}'::jsonb",
                )
            )

            assert await _direct_projection_column_grants(connection) == EXPECTED_COLUMN_GRANTS
            for table_name in (
                "tenants",
                "users",
                "user_roles",
                "user_activation_tokens",
                "outbox_events",
            ):
                assert not await connection.scalar(
                    text(
                        "select pg_catalog.has_table_privilege(:role_name, :table_name, 'INSERT')"
                    ),
                    {
                        "role_name": PROJECTION_ROLE,
                        "table_name": f"public.{table_name}",
                    },
                )
            for table_name in (
                "users",
                "user_roles",
                "user_activation_tokens",
                "outbox_events",
            ):
                assert not await connection.scalar(
                    text(
                        "select pg_catalog.has_table_privilege(:role_name, :table_name, 'INSERT')"
                    ),
                    {
                        "role_name": PLATFORM_APPLICATION_ROLE,
                        "table_name": f"public.{table_name}",
                    },
                )
            for table_name, privilege in (
                ("user_activation_tokens", "SELECT"),
                ("user_activation_tokens", "UPDATE"),
                ("outbox_events", "SELECT"),
            ):
                assert not await connection.scalar(
                    text(
                        "select pg_catalog.has_table_privilege(:role_name, :table_name, :privilege)"
                    ),
                    {
                        "role_name": PLATFORM_APPLICATION_ROLE,
                        "table_name": f"public.{table_name}",
                        "privilege": privilege,
                    },
                )
    finally:
        await engine.dispose()


async def _call_gateway(
    database_url: URL,
    request: GatewayRequest,
    *,
    insert_tenant: bool = False,
    assume_platform_role: bool = False,
) -> object | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if assume_platform_role:
                await connection.exec_driver_sql(f'SET LOCAL ROLE "{PLATFORM_APPLICATION_ROLE}"')
                assert await connection.scalar(text("select current_user")) == (
                    PLATFORM_APPLICATION_ROLE
                )
            if insert_tenant:
                await _insert_tenant(connection, request)
            return await connection.scalar(GATEWAY_CALL, request.parameters)
    finally:
        await engine.dispose()


async def _call_reissue_gateway(
    database_url: URL,
    request: ReissueGatewayRequest,
    *,
    assume_platform_role: bool = False,
) -> object | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if assume_platform_role:
                await connection.exec_driver_sql(f'SET LOCAL ROLE "{PLATFORM_APPLICATION_ROLE}"')
                assert await connection.scalar(text("select current_user")) == (
                    PLATFORM_APPLICATION_ROLE
                )
            return await connection.scalar(
                REISSUE_GATEWAY_CALL,
                request.parameters,
            )
    finally:
        await engine.dispose()


async def _call_correction_gateway(
    database_url: URL,
    request: CorrectionGatewayRequest,
    *,
    assume_platform_role: bool = False,
) -> object | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if assume_platform_role:
                await connection.exec_driver_sql(f'SET LOCAL ROLE "{PLATFORM_APPLICATION_ROLE}"')
                assert await connection.scalar(text("select current_user")) == (
                    PLATFORM_APPLICATION_ROLE
                )
            return await connection.scalar(
                CORRECTION_GATEWAY_CALL,
                request.parameters,
            )
    finally:
        await engine.dispose()


async def _call_reissue_gateways_concurrently(
    database_url: URL,
    requests: tuple[ReissueGatewayRequest, ReissueGatewayRequest],
) -> tuple[object | None, object | None]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    async def call(request: ReissueGatewayRequest) -> object | None:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'SET LOCAL ROLE "{PLATFORM_APPLICATION_ROLE}"')
            assert await connection.scalar(text("select current_user")) == (
                PLATFORM_APPLICATION_ROLE
            )
            await ready.put(None)
            await release.wait()
            return await connection.scalar(
                REISSUE_GATEWAY_CALL,
                request.parameters,
            )

    tasks = tuple(asyncio.create_task(call(request)) for request in requests)
    try:
        await ready.get()
        await ready.get()
        release.set()
        return tuple(
            await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=15,
            )
        )
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


async def _call_correction_and_reissue_concurrently(
    database_url: URL,
    *,
    correction: CorrectionGatewayRequest,
    reissue: ReissueGatewayRequest,
) -> tuple[object | None, object | None]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    ready: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()

    async def call(statement: TextClause, parameters: dict[str, object]) -> object | None:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'SET LOCAL ROLE "{PLATFORM_APPLICATION_ROLE}"')
            await ready.put(None)
            await release.wait()
            return await connection.scalar(statement, parameters)

    tasks = (
        asyncio.create_task(call(CORRECTION_GATEWAY_CALL, correction.parameters)),
        asyncio.create_task(call(REISSUE_GATEWAY_CALL, reissue.parameters)),
    )
    try:
        await ready.get()
        await ready.get()
        release.set()
        return tuple(await asyncio.wait_for(asyncio.gather(*tasks), timeout=15))
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


async def _insert_tenant(
    connection: AsyncConnection,
    request: GatewayRequest,
) -> None:
    await connection.execute(
        text(
            "insert into public.tenants ("
            "id, slug, name, status, plan_code, data_region, locale, timezone"
            ") values ("
            ":tenant_id, :slug, :name, 'provisioning', 'core', "
            "'tr-1', 'tr-TR', 'Europe/Istanbul'"
            ")"
        ),
        {
            "tenant_id": request.tenant_id,
            "slug": request.slug,
            "name": request.full_name,
        },
    )


async def _insert_tenant_without_initial_admin(
    database_url: URL,
    request: GatewayRequest,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await _insert_tenant(connection, request)
    finally:
        await engine.dispose()


async def _seed_identity(
    database_url: URL,
    *,
    identity_id: UUID,
    email: str,
    status: str,
    password_hash: str,
    platform_permission_version: int,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into public.identities ("
                    "id, email, status, password_hash, platform_permission_version"
                    ") values ("
                    ":identity_id, :email, :status, :password_hash, "
                    ":platform_permission_version"
                    ")"
                ),
                {
                    "identity_id": identity_id,
                    "email": email,
                    "status": status,
                    "password_hash": password_hash,
                    "platform_permission_version": platform_permission_version,
                },
            )
    finally:
        await engine.dispose()


async def _seed_identity_tenant_membership(
    database_url: URL,
    *,
    tenant_id: UUID,
    identity_id: UUID,
    user_id: UUID,
    email: str,
    password_hash: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into public.users ("
                    "id, tenant_id, email, full_name, status, password_hash, "
                    "can_invite_users, permission_version"
                    ") values ("
                    ":user_id, :tenant_id, :email, 'Existing Tenant Member', "
                    "'active', :password_hash, false, 1"
                    ")"
                ),
                {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "email": email,
                    "password_hash": password_hash,
                },
            )
            await connection.execute(
                text(
                    "insert into public.tenant_memberships ("
                    "id, tenant_id, identity_id, legacy_user_id, full_name, "
                    "status, permission_version"
                    ") values ("
                    ":user_id, :tenant_id, :identity_id, :user_id, "
                    "'Existing Tenant Member', 'active', 1"
                    ")"
                ),
                {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "identity_id": identity_id,
                },
            )
    finally:
        await engine.dispose()


async def _identity_exists(database_url: URL, identity_id: UUID) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("select exists(select 1 from public.identities where id = :identity_id)"),
                    {"identity_id": identity_id},
                )
            )
    finally:
        await engine.dispose()


async def _identity_security_state(
    database_url: URL,
    identity_id: UUID,
) -> tuple[object, ...]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select id, email, email_normalized, status, password_hash, "
                        "platform_permission_version, created_at, updated_at "
                        "from public.identities where id = :identity_id"
                    ),
                    {"identity_id": identity_id},
                )
            ).one()
            return tuple(row)
    finally:
        await engine.dispose()


async def _seed_decoy_invited_tenant_admin(
    database_url: URL,
    *,
    tenant_id: UUID,
    label: str,
) -> UUID:
    user_id = uuid4()
    identity_id = uuid4()
    email = f"{label}.{uuid4().hex[:12]}@example.test"
    full_name = f"{label.replace('-', ' ').title()} Admin"
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into public.identities ("
                    "id, email, status, password_hash, platform_permission_version"
                    ") values ("
                    ":identity_id, :email, 'active', :password_hash, 1"
                    ")"
                ),
                {
                    "identity_id": identity_id,
                    "email": email,
                    "password_hash": "$argon2id$decoy-credential-must-not-change",
                },
            )
            await connection.execute(
                text(
                    "insert into public.users ("
                    "id, tenant_id, email, full_name, status, password_hash, "
                    "can_invite_users, permission_version"
                    ") values ("
                    ":user_id, :tenant_id, :email, :full_name, 'invited', "
                    "null, false, 1"
                    ")"
                ),
                {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "email": email,
                    "full_name": full_name,
                },
            )
            await connection.execute(
                text(
                    "insert into public.user_roles ("
                    "tenant_id, user_id, role_id, role_scope_type, active"
                    ") values ("
                    ":tenant_id, :user_id, :role_id, 'tenant', true"
                    ")"
                ),
                {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "role_id": TENANT_ADMIN_ROLE_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into public.tenant_memberships ("
                    "id, tenant_id, identity_id, legacy_user_id, full_name, "
                    "status, permission_version"
                    ") values ("
                    ":user_id, :tenant_id, :identity_id, :user_id, :full_name, "
                    "'invited', 1"
                    ")"
                ),
                {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "identity_id": identity_id,
                    "full_name": full_name,
                },
            )
            await connection.execute(
                text(
                    "insert into public.membership_roles ("
                    "tenant_id, membership_id, role_id, role_scope_type, active"
                    ") values ("
                    ":tenant_id, :user_id, :role_id, 'tenant', true"
                    ")"
                ),
                {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "role_id": TENANT_ADMIN_ROLE_ID,
                },
            )
    finally:
        await engine.dispose()
    return user_id


async def _mark_initial_admin_activated(
    database_url: URL,
    request: GatewayRequest,
) -> None:
    password_hash = "$argon2id$activated-credential"
    now = datetime.now(UTC)
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            identity_id = await connection.scalar(
                text(
                    "select identity_id from public.tenant_memberships "
                    "where tenant_id = :tenant_id and legacy_user_id = :user_id"
                ),
                {
                    "tenant_id": request.tenant_id,
                    "user_id": request.user_id,
                },
            )
            assert identity_id is not None
            await connection.execute(
                text(
                    "update public.identities "
                    "set status = 'active', password_hash = :password_hash, "
                    "updated_at = :now "
                    "where id = :identity_id"
                ),
                {
                    "identity_id": identity_id,
                    "password_hash": password_hash,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "update public.users "
                    "set status = 'active', password_hash = :password_hash, "
                    "updated_at = :now "
                    "where tenant_id = :tenant_id and id = :user_id"
                ),
                {
                    "tenant_id": request.tenant_id,
                    "user_id": request.user_id,
                    "password_hash": password_hash,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "update public.tenant_memberships "
                    "set status = 'active', updated_at = :now "
                    "where tenant_id = :tenant_id and legacy_user_id = :user_id"
                ),
                {
                    "tenant_id": request.tenant_id,
                    "user_id": request.user_id,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "update public.user_activation_tokens "
                    "set consumed_at = :now, updated_at = :now "
                    "where tenant_id = :tenant_id and id = :activation_id"
                ),
                {
                    "tenant_id": request.tenant_id,
                    "activation_id": request.activation_id,
                    "now": now,
                },
            )
    finally:
        await engine.dispose()


async def _set_initial_admin_membership_status(
    database_url: URL,
    request: GatewayRequest,
    *,
    status: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update public.tenant_memberships "
                    "set status = :status, updated_at = :now "
                    "where tenant_id = :tenant_id and legacy_user_id = :user_id"
                ),
                {
                    "tenant_id": request.tenant_id,
                    "user_id": request.user_id,
                    "status": status,
                    "now": datetime.now(UTC),
                },
            )
    finally:
        await engine.dispose()


async def _invitation_history(
    database_url: URL,
    tenant_id: UUID,
) -> dict[str, tuple[dict[str, object], ...]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            queries = {
                "users": (
                    "select id, email, full_name, status, password_hash, "
                    "can_invite_users, permission_version, created_at, updated_at "
                    "from public.users where tenant_id = :tenant_id order by id"
                ),
                "identities": (
                    "select identities.id, identities.email, identities.email_normalized, "
                    "identities.status, identities.password_hash, "
                    "identities.platform_permission_version, identities.created_at, "
                    "identities.updated_at "
                    "from public.identities as identities "
                    "join public.tenant_memberships as memberships "
                    "on memberships.identity_id = identities.id "
                    "where memberships.tenant_id = :tenant_id "
                    "order by identities.id"
                ),
                "memberships": (
                    "select id, identity_id, legacy_user_id, full_name, status, "
                    "permission_version, created_at, updated_at "
                    "from public.tenant_memberships "
                    "where tenant_id = :tenant_id order by id"
                ),
                "user_roles": (
                    "select user_id, role_id, role_scope_type, active, "
                    "created_at, updated_at "
                    "from public.user_roles where tenant_id = :tenant_id "
                    "order by user_id, role_id"
                ),
                "membership_roles": (
                    "select membership_id, role_id, role_scope_type, active, "
                    "created_at, updated_at "
                    "from public.membership_roles where tenant_id = :tenant_id "
                    "order by membership_id, role_id"
                ),
                "activations": (
                    "select id, user_id, token_hash, expires_at, consumed_at, "
                    "revoked_at, created_at, updated_at "
                    "from public.user_activation_tokens "
                    "where tenant_id = :tenant_id order by id"
                ),
                "outbox_events": (
                    "select id, aggregate_type, aggregate_id, event_type, payload, "
                    "source_key, occurred_at "
                    "from public.outbox_events where tenant_id = :tenant_id "
                    "order by id"
                ),
            }
            history: dict[str, tuple[dict[str, object], ...]] = {}
            for key, query in queries.items():
                rows = (
                    await connection.execute(
                        text(query),
                        {"tenant_id": tenant_id},
                    )
                ).mappings()
                history[key] = tuple(dict(row) for row in rows)
            return history
    finally:
        await engine.dispose()


def _assert_stable_invitation_principals(
    before: dict[str, tuple[dict[str, object], ...]],
    after: dict[str, tuple[dict[str, object], ...]],
) -> None:
    for key in (
        "users",
        "identities",
        "memberships",
        "user_roles",
        "membership_roles",
    ):
        assert after[key] == before[key]


def _assert_reissue_history(
    history: dict[str, tuple[dict[str, object], ...]],
    *,
    original: GatewayRequest,
    reissues: tuple[ReissueGatewayRequest, ...],
    expected_live_ids: set[UUID],
) -> None:
    activations = {activation["id"]: activation for activation in history["activations"]}
    expected_activation_ids = {
        original.activation_id,
        *(request.activation_id for request in reissues),
    }
    assert set(activations) == expected_activation_ids
    assert {activation["user_id"] for activation in activations.values()} == {original.user_id}
    assert len({activation["token_hash"] for activation in activations.values()}) == len(
        activations
    )
    assert all(activation["consumed_at"] is None for activation in activations.values())
    assert {
        activation_id
        for activation_id, activation in activations.items()
        if activation["revoked_at"] is None
    } == expected_live_ids
    assert activations[original.activation_id]["revoked_at"] is not None
    assert activations[original.activation_id]["token_hash"] == original.token_hash
    for request in reissues:
        activation = activations[request.activation_id]
        assert activation["token_hash"] == request.token_hash
        assert activation["expires_at"] == request.expires_at

    outbox_events = {outbox["id"]: outbox for outbox in history["outbox_events"]}
    assert set(outbox_events) == {
        original.outbox_id,
        *(request.outbox_id for request in reissues),
    }
    assert len({outbox["source_key"] for outbox in outbox_events.values()}) == len(outbox_events)
    original_outbox = outbox_events[original.outbox_id]
    assert {
        key: original_outbox[key]
        for key in (
            "id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "payload",
            "source_key",
        )
    } == {
        "id": original.outbox_id,
        "aggregate_type": "identity_membership",
        "aggregate_id": original.user_id,
        "event_type": INVITATION_EVENT_TYPE,
        "payload": {
            "recipient_user_id": str(original.user_id),
            "activation_id": str(original.activation_id),
        },
        "source_key": f"{INVITATION_EVENT_TYPE}:{original.user_id}",
    }
    for request in reissues:
        outbox = outbox_events[request.outbox_id]
        assert outbox["aggregate_type"] == "identity_membership"
        assert outbox["aggregate_id"] == original.user_id
        assert outbox["event_type"] == INVITATION_EVENT_TYPE
        assert outbox["payload"] == {
            "recipient_user_id": str(original.user_id),
            "activation_id": str(request.activation_id),
        }
        assert outbox["source_key"] == (
            f"{INVITATION_EVENT_TYPE}:{original.user_id}:reissue:{request.activation_id}"
        )


async def _tenant_projection(
    database_url: URL,
    tenant_id: UUID,
) -> dict[str, object]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            user = tuple(
                (
                    await connection.execute(
                        text(
                            "select id, email, full_name, status, password_hash, "
                            "can_invite_users, permission_version "
                            "from public.users where tenant_id = :tenant_id"
                        ),
                        {"tenant_id": tenant_id},
                    )
                ).one()
            )
            membership_row = (
                await connection.execute(
                    text(
                        "select id, identity_id, full_name, status, permission_version "
                        "from public.tenant_memberships where tenant_id = :tenant_id"
                    ),
                    {"tenant_id": tenant_id},
                )
            ).one()
            membership = tuple(membership_row)
            identity = tuple(
                (
                    await connection.execute(
                        text(
                            "select id, email, status, password_hash, "
                            "platform_permission_version "
                            "from public.identities where id = :identity_id"
                        ),
                        {"identity_id": membership_row.identity_id},
                    )
                ).one()
            )
            user_roles = tuple(
                (
                    row.role_id,
                    row.role_scope_type,
                    bool(row.active),
                )
                for row in (
                    await connection.execute(
                        text(
                            "select role_id, role_scope_type, active "
                            "from public.user_roles where tenant_id = :tenant_id "
                            "order by role_id"
                        ),
                        {"tenant_id": tenant_id},
                    )
                )
            )
            membership_roles = tuple(
                (
                    row.role_id,
                    row.role_scope_type,
                    bool(row.active),
                )
                for row in (
                    await connection.execute(
                        text(
                            "select role_id, role_scope_type, active "
                            "from public.membership_roles where tenant_id = :tenant_id "
                            "order by role_id"
                        ),
                        {"tenant_id": tenant_id},
                    )
                )
            )
            activation = tuple(
                (
                    await connection.execute(
                        text(
                            "select id, user_id, token_hash, expires_at, "
                            "consumed_at, revoked_at "
                            "from public.user_activation_tokens "
                            "where tenant_id = :tenant_id"
                        ),
                        {"tenant_id": tenant_id},
                    )
                ).one()
            )
            outbox = (
                (
                    await connection.execute(
                        text(
                            "select id, aggregate_type, aggregate_id, event_type, "
                            "payload, source_key "
                            "from public.outbox_events where tenant_id = :tenant_id"
                        ),
                        {"tenant_id": tenant_id},
                    )
                )
                .mappings()
                .one()
            )
            platform_role_count = int(
                await connection.scalar(
                    text(
                        "select count(*) from public.platform_identity_roles "
                        "where identity_id = :identity_id"
                    ),
                    {"identity_id": membership_row.identity_id},
                )
            )
            return {
                "user": user,
                "identity": identity,
                "membership": membership,
                "user_roles": user_roles,
                "membership_roles": membership_roles,
                "activation": activation,
                "outbox": dict(outbox),
                "platform_role_count": platform_role_count,
            }
    finally:
        await engine.dispose()


def _assert_only_tenant_admin_role(
    projection: dict[str, object],
    user_id: UUID,
) -> None:
    expected = ((TENANT_ADMIN_ROLE_ID, "tenant", True),)
    assert projection["user_roles"] == expected
    assert projection["membership_roles"] == expected
    assert projection["membership"][0] == user_id
    assert projection["platform_role_count"] == 0


def _assert_activation_and_outbox(
    projection: dict[str, object],
    request: GatewayRequest,
) -> None:
    activation = projection["activation"]
    assert activation[:3] == (
        request.activation_id,
        request.user_id,
        request.token_hash,
    )
    assert activation[3] == request.expires_at
    assert activation[4:] == (None, None)

    outbox = projection["outbox"]
    assert outbox == {
        "id": request.outbox_id,
        "aggregate_type": "identity_membership",
        "aggregate_id": request.user_id,
        "event_type": INVITATION_EVENT_TYPE,
        "payload": {
            "recipient_user_id": str(request.user_id),
            "activation_id": str(request.activation_id),
        },
        "source_key": f"{INVITATION_EVENT_TYPE}:{request.user_id}",
    }


async def _tenant_row_count(
    database_url: URL,
    tenant_id: UUID,
) -> tuple[int, int, int, int, int, int]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return tuple(
                int(value)
                for value in (
                    await connection.execute(
                        text(
                            "select "
                            "(select count(*) from public.tenants where id = :tenant_id), "
                            "(select count(*) from public.users where tenant_id = :tenant_id), "
                            "(select count(*) from public.tenant_memberships "
                            " where tenant_id = :tenant_id), "
                            "(select count(*) from public.user_roles "
                            " where tenant_id = :tenant_id), "
                            "(select count(*) from public.user_activation_tokens "
                            " where tenant_id = :tenant_id), "
                            "(select count(*) from public.outbox_events "
                            " where tenant_id = :tenant_id)"
                        ),
                        {"tenant_id": tenant_id},
                    )
                ).one()
            )
    finally:
        await engine.dispose()


async def _create_login_role(
    database_url: URL,
    role_name: str,
    *,
    capability_role: str | None = None,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quoted_role = connection.dialect.identifier_preparer.quote(role_name)
            await connection.exec_driver_sql(
                f"CREATE ROLE {quoted_role} LOGIN NOSUPERUSER NOBYPASSRLS "
                "NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT"
            )
            if capability_role is not None:
                quoted_capability = connection.dialect.identifier_preparer.quote(capability_role)
                await connection.exec_driver_sql(
                    f"GRANT {quoted_capability} TO {quoted_role} "
                    "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
                )
    finally:
        await engine.dispose()


async def _drop_login_role(
    database_url: URL,
    role_name: str,
    *,
    capability_role: str | None = None,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("select exists(select 1 from pg_catalog.pg_roles where rolname = :role_name)"),
                {"role_name": role_name},
            )
            if not exists:
                return
            quoted_role = connection.dialect.identifier_preparer.quote(role_name)
            await connection.exec_driver_sql(f"DROP OWNED BY {quoted_role}")
            if capability_role is not None:
                quoted_capability = connection.dialect.identifier_preparer.quote(capability_role)
                await connection.exec_driver_sql(f"REVOKE {quoted_capability} FROM {quoted_role}")
            await connection.exec_driver_sql(f"DROP ROLE {quoted_role}")
    finally:
        await engine.dispose()


async def _prepare_0044_migration_owner(
    database_url: URL,
    role_name: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            quoted_role = connection.dialect.identifier_preparer.quote(role_name)
            quote = connection.dialect.identifier_preparer.quote
            for table_name in MIGRATION_OWNED_TABLES:
                await connection.exec_driver_sql(
                    f"ALTER TABLE public.{quote(table_name)} OWNER TO {quoted_role}"
                )
    finally:
        await engine.dispose()


async def _remove_0044_migration_owner(
    database_url: URL,
    role_name: str,
    *,
    replacement_owner: str,
) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            if not await connection.scalar(
                text("select exists(select 1 from pg_catalog.pg_roles where rolname = :role_name)"),
                {"role_name": role_name},
            ):
                return
            quote = connection.dialect.identifier_preparer.quote
            quoted_role = quote(role_name)
            quoted_replacement = quote(replacement_owner)
            quoted_projection = quote(PROJECTION_ROLE)
            await connection.exec_driver_sql(
                f"REASSIGN OWNED BY {quoted_role} TO {quoted_replacement}"
            )
            await connection.exec_driver_sql(f"REVOKE {quoted_projection} FROM {quoted_role}")
            await connection.exec_driver_sql(f"DROP OWNED BY {quoted_role}")
            await connection.exec_driver_sql(f"DROP ROLE {quoted_role}")
    finally:
        await engine.dispose()


async def _set_only_role_state(
    database_url: URL,
    role_name: str,
) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select role.rolcanlogin, role.rolsuper, role.rolbypassrls, "
                        "role.rolinherit, role.rolcreatedb, role.rolcreaterole, "
                        "role.rolreplication, "
                        "pg_catalog.pg_has_role(:role_name, :projection_role, 'SET'), "
                        "pg_catalog.pg_has_role(:role_name, :projection_role, 'USAGE') "
                        "from pg_catalog.pg_roles as role "
                        "where role.rolname = :role_name"
                    ),
                    {
                        "role_name": role_name,
                        "projection_role": PROJECTION_ROLE,
                    },
                )
            ).one()
            return tuple(bool(value) for value in row)
    finally:
        await engine.dispose()


async def _direct_projection_column_grants(
    connection: AsyncConnection,
) -> set[tuple[str, str, str]]:
    rows = await connection.execute(
        text(
            "select table_class.relname, attribute.attname, privilege.privilege_type "
            "from pg_catalog.pg_attribute as attribute "
            "join pg_catalog.pg_class as table_class "
            "on table_class.oid = attribute.attrelid "
            "join pg_catalog.pg_namespace as namespace "
            "on namespace.oid = table_class.relnamespace "
            "cross join lateral pg_catalog.aclexplode(attribute.attacl) as privilege "
            "join pg_catalog.pg_roles as grantee "
            "on grantee.oid = privilege.grantee "
            "where namespace.nspname = 'public' "
            "and table_class.relname = any(:table_names) "
            "and grantee.rolname = :role_name"
        ),
        {
            "table_names": [
                "tenants",
                "users",
                "user_roles",
                "user_activation_tokens",
                "outbox_events",
            ],
            "role_name": PROJECTION_ROLE,
        },
    )
    return {(str(row[0]), str(row[1]), str(row[2])) for row in rows}


async def _projection_column_grants(
    database_url: URL,
) -> set[tuple[str, str, str]]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await _direct_projection_column_grants(connection)
    finally:
        await engine.dispose()


async def _gateway_exists(database_url: URL) -> bool:
    return await _function_exists(database_url, FUNCTION_REGPROCEDURE)


async def _function_exists(
    database_url: URL,
    signature: str,
) -> bool:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return (
                await connection.scalar(
                    text("select pg_catalog.to_regprocedure(:signature) is not null"),
                    {"signature": signature},
                )
                is True
            )
    finally:
        await engine.dispose()


async def _initial_admin_policy_count(database_url: URL) -> int:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int(
                await connection.scalar(
                    text(
                        "select count(*) from pg_catalog.pg_policies "
                        "where schemaname = 'public' "
                        "and policyname like 'platform_initial_admin_%'"
                    )
                )
            )
    finally:
        await engine.dispose()


async def _outbox_event_constraint(database_url: URL) -> str:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return str(
                await connection.scalar(
                    text(
                        "select pg_catalog.pg_get_constraintdef(constraint_row.oid) "
                        "from pg_catalog.pg_constraint as constraint_row "
                        "where constraint_row.conname = 'ck_outbox_events_event_type' "
                        "and constraint_row.conrelid = 'public.outbox_events'::regclass"
                    )
                )
            )
    finally:
        await engine.dispose()


async def _current_revision(database_url: URL) -> str:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return str(await connection.scalar(text("select version_num from alembic_version")))
    finally:
        await engine.dispose()


async def _row_security_flags(
    database_url: URL,
    table_name: str,
) -> tuple[bool, bool]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "select table_class.relrowsecurity, table_class.relforcerowsecurity "
                        "from pg_catalog.pg_class as table_class "
                        "join pg_catalog.pg_namespace as namespace "
                        "on namespace.oid = table_class.relnamespace "
                        "where namespace.nspname = 'public' "
                        "and table_class.relname = :table_name"
                    ),
                    {"table_name": table_name},
                )
            ).one()
            return bool(row[0]), bool(row[1])
    finally:
        await engine.dispose()
