from app.services.platform_tenant_queries import _metadata_statement


def test_platform_metadata_projection_references_only_tenant_root_columns() -> None:
    sql = " ".join(str(_metadata_statement()).lower().split())

    assert " from tenants" in sql
    assert " join " not in sql
    for forbidden_table in (
        "employees",
        "users",
        "leave_requests",
        "leave_balance_summaries",
        "command_idempotency",
    ):
        assert forbidden_table not in sql
    for forbidden_counter in ("count(", "sum(", "avg(", "employee_count"):
        assert forbidden_counter not in sql
