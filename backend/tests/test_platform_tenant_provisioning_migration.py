from pathlib import Path

MIGRATION = Path("backend/alembic/versions/0044_platform_initial_tenant_admin.py")


def test_platform_initial_admin_migration_defines_only_a_narrow_gateway() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0044_platform_initial_tenant_admin"' in source
    assert 'down_revision: str | None = "0043_p11_employee_lifecycle_profile_lock"' in source
    assert "SECURITY DEFINER" in source
    assert "SET search_path = pg_catalog, public" in source
    assert "provision_platform_initial_tenant_admin" in source
    assert "correct_platform_initial_tenant_admin_invitation" in source
    assert "reissue_platform_initial_tenant_admin_invitation" in source
    assert "sync_current_tenant_identity_membership" in source
    assert "identity.initial_admin_invited" in source
    assert "AS RESTRICTIVE FOR INSERT" in source
    assert "event_type <> 'identity.initial_admin_invited'" in source
    assert "d2000000-0000-4000-8000-000000000002" in source
    assert "ERRCODE = 'WF003'" in source
    assert "REVOKE ALL ON FUNCTION" in source
    assert "FROM PUBLIC" in source
    assert "GRANT EXECUTE ON FUNCTION" in source
    assert "TO wealthy_falcon_platform" in source
    assert "':correction:' || requested_activation_id::text" in source
    assert "WHEN unique_violation THEN" in source
    assert "DROP FUNCTION" in source
    assert "downgrade refused" in source
    assert "requested_activation_path" not in source
    assert "'activation_path'" not in source

    for forbidden_grant in (
        "GRANT INSERT ON users TO wealthy_falcon_platform",
        "GRANT INSERT ON identities TO wealthy_falcon_platform",
        "GRANT INSERT ON tenant_memberships TO wealthy_falcon_platform",
        "GRANT INSERT ON user_activation_tokens TO wealthy_falcon_platform",
        "GRANT INSERT ON outbox_events TO wealthy_falcon_platform",
    ):
        assert forbidden_grant not in source


def test_downgrade_assumes_projection_owner_before_gateway_acl_cleanup() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source[source.index("def downgrade()") :]

    set_role = downgrade.index('SET LOCAL ROLE "{_PROJECTION_ROLE}"')
    revoke_execute = downgrade.index("REVOKE EXECUTE ON FUNCTION")
    drop_function = downgrade.index("DROP FUNCTION IF EXISTS")
    reset_role = downgrade.index("RESET ROLE")

    assert set_role < revoke_execute < drop_function < reset_role


def test_notification_delivery_claim_lifecycle_has_schema_and_downgrade_parity() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for column_name in (
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
    ):
        assert f'sa.Column("{column_name}"' in source

    assert "ck_notification_deliveries_lease" in source
    assert "ck_notification_deliveries_prepared_message" in source
    assert "lease_attempt = attempt_count" in source
    assert "_remove_notification_delivery_lifecycle()" in source
    assert "reversed(_DELIVERY_UPDATE_COLUMNS)" in source
