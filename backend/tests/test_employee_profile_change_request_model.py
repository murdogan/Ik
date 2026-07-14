from app.models.employee_profile_change_request import EmployeeProfileChangeRequest


def test_change_request_model_is_strongly_typed_and_has_required_guards() -> None:
    table = EmployeeProfileChangeRequest.__table__

    assert {column.name for column in table.c} == {
        "id",
        "tenant_id",
        "employee_id",
        "requester_membership_id",
        "requester_user_id",
        "status",
        "version",
        "base_profile_version",
        "preferred_name_changed",
        "previous_preferred_name",
        "proposed_preferred_name",
        "phone_changed",
        "previous_phone",
        "proposed_phone",
        "birth_date_changed",
        "previous_birth_date",
        "proposed_birth_date",
        "submitted_at",
        "decided_at",
        "cancelled_at",
        "decided_by_membership_id",
        "decided_by_user_id",
        "rejection_reason",
        "created_at",
        "updated_at",
    }
    assert "changes" not in table.c
    assert "payload" not in table.c
    assert "metadata" not in table.c
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_employee_profile_change_requests_status",
        "ck_employee_profile_change_requests_version_positive",
        "ck_employee_profile_change_requests_base_version_positive",
        "ck_employee_profile_change_requests_has_change",
        "ck_employee_profile_change_requests_preferred_snapshot",
        "ck_employee_profile_change_requests_phone_snapshot",
        "ck_employee_profile_change_requests_birth_snapshot",
        "ck_employee_profile_change_requests_state",
        "ck_employee_profile_change_requests_timestamp_order",
        "fk_epcr_tenant_employee_employees",
        "fk_epcr_requester_membership_memberships",
        "fk_epcr_requester_user_users",
        "fk_epcr_decider_membership_memberships",
        "fk_epcr_decider_user_users",
    }
    indexes = {index.name: index for index in table.indexes}
    assert indexes["uq_employee_profile_change_requests_active_employee"].unique
    queue_cursor = indexes["ix_employee_profile_change_requests_tenant_queue_cursor"]
    assert [column.name for column in queue_cursor.columns] == [
        "tenant_id",
        "status",
        "submitted_at",
        "id",
    ]
    assert EmployeeProfileChangeRequest.__mapper__.version_id_col is table.c.version
