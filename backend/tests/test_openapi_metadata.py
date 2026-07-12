from app.api.errors import TENANT_ID_HEADER, TENANT_SLUG_HEADER
from app.api.openapi import (
    DASHBOARD_TAG,
    EMPLOYEES_TAG,
    LEAVE_BALANCES_TAG,
    LEAVE_REQUESTS_TAG,
    OPENAPI_TAGS,
    PLATFORM_TENANTS_TAG,
    PUBLIC_TAG,
    SYSTEM_TAG,
    TENANT_SETTINGS_TAG,
)
from app.main import create_app
from app.schemas.employee import EMPLOYEE_LIST_DEFAULT_LIMIT, EMPLOYEE_LIST_MAX_LIMIT
from app.schemas.leave_request import (
    LEAVE_REQUEST_LIST_DEFAULT_LIMIT,
    LEAVE_REQUEST_LIST_MAX_LIMIT,
)
from app.schemas.tenant import TENANT_LIST_DEFAULT_LIMIT, TENANT_LIST_MAX_LIMIT
from fastapi.testclient import TestClient

HTTP_METHODS = {"delete", "get", "patch", "post", "put"}
PLATFORM_TENANT_OPERATIONS = {
    ("/api/v1/platform/tenants", "post"),
    ("/api/v1/platform/tenants", "get"),
    ("/api/v1/platform/tenants/{tenant_id}", "get"),
    ("/api/v1/platform/tenants/{tenant_id}", "patch"),
    ("/api/v1/platform/tenants/{tenant_id}/features", "get"),
    ("/api/v1/platform/tenants/{tenant_id}/features", "patch"),
}
TENANT_PRINCIPAL_OPERATIONS = {
    ("/api/v1/tenant", "get"),
    ("/api/v1/tenant/features", "get"),
    ("/api/v1/tenant/settings", "get"),
    ("/api/v1/tenant/settings", "patch"),
}
FEATURE_OPERATIONS = {
    ("/api/v1/platform/tenants/{tenant_id}/features", "get"),
    ("/api/v1/platform/tenants/{tenant_id}/features", "patch"),
    ("/api/v1/tenant/features", "get"),
}


def test_openapi_uses_readable_tag_catalog() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["tags"] == OPENAPI_TAGS
    descriptions = {tag["name"]: tag["description"] for tag in response.json()["tags"]}
    assert "service health, version, and environment readiness" in descriptions[SYSTEM_TAG]
    assert "outside the tenant-scoped JSON API" in descriptions[PUBLIC_TAG]
    assert "Default-deny platform provisioning" in descriptions[PLATFORM_TENANTS_TAG]
    assert "configured limits" in descriptions[PLATFORM_TENANTS_TAG]
    assert "allowlisted rollout flags" in descriptions[PLATFORM_TENANTS_TAG]
    assert "never HR data" in descriptions[PLATFORM_TENANTS_TAG]
    assert "fixed typed settings allowlist" in descriptions[TENANT_SETTINGS_TAG]
    assert "read-only effective module flags" in descriptions[TENANT_SETTINGS_TAG]
    assert "lifecycle-aware behavior" in descriptions[TENANT_SETTINGS_TAG]
    assert "department distribution, new starters" in descriptions[DASHBOARD_TAG]
    assert "employee master data" in descriptions[EMPLOYEES_TAG]
    assert "no accrual engine" in descriptions[LEAVE_BALANCES_TAG]
    assert "filtered review queues" in descriptions[LEAVE_REQUESTS_TAG]


def test_current_operations_have_readable_openapi_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_metadata = {
        ("/health", "get"): (
            SYSTEM_TAG,
            "Check API health",
            "service availability",
        ),
        ("/", "get"): (
            PUBLIC_TAG,
            "Serve public landing page",
            "outside the tenant-scoped JSON API surface",
        ),
        ("/api/v1/platform/tenants", "post"): (
            PLATFORM_TENANTS_TAG,
            "Provision platform tenant",
            "server generates the tenant ID",
        ),
        ("/api/v1/platform/tenants", "get"): (
            PLATFORM_TENANTS_TAG,
            "List platform tenant metadata",
            "do not join, count, or expose employees, users, leave records",
        ),
        ("/api/v1/platform/tenants/{tenant_id}", "get"): (
            PLATFORM_TENANTS_TAG,
            "Read platform tenant metadata",
            "path UUID selects a resource only",
        ),
        ("/api/v1/platform/tenants/{tenant_id}", "patch"): (
            PLATFORM_TENANTS_TAG,
            "Update platform tenant lifecycle",
            "Closed is terminal, offboarding is closure-only",
        ),
        ("/api/v1/platform/tenants/{tenant_id}/features", "get"): (
            PLATFORM_TENANTS_TAG,
            "Read platform tenant feature flags",
            "No employee, user, leave, document, or HR-derived usage data",
        ),
        ("/api/v1/platform/tenants/{tenant_id}/features", "patch"): (
            PLATFORM_TENANTS_TAG,
            "Update platform tenant feature flags",
            "Unknown, duplicate, null, numeric, string, and arbitrary nested flag values",
        ),
        ("/api/v1/tenant", "get"): (
            TENANT_SETTINGS_TAG,
            "Read current tenant metadata",
            "user IDs, and tenant IDs do not select or authorize this resource",
        ),
        ("/api/v1/tenant/features", "get"): (
            TENANT_SETTINGS_TAG,
            "Read current tenant feature flags",
            "cannot switch tenant scope",
        ),
        ("/api/v1/tenant/settings", "get"): (
            TENANT_SETTINGS_TAG,
            "Read typed tenant settings",
            "fixed locale, IANA timezone, week-start, date-format, and time-format settings",
        ),
        ("/api/v1/tenant/settings", "patch"): (
            TENANT_SETTINGS_TAG,
            "Update typed tenant settings",
            "Arbitrary keys, null values, nested settings bags",
        ),
        ("/api/v1/dashboard/summary", "get"): (
            DASHBOARD_TAG,
            "Read tenant dashboard summary",
            "active workforce counts",
        ),
        ("/api/v1/employees", "get"): (
            EMPLOYEES_TAG,
            "List tenant employees",
            "tenant isolation is applied before bounded keyset pagination",
        ),
        ("/api/v1/employees", "post"): (
            EMPLOYEES_TAG,
            "Create tenant employee",
            "lifecycle date rules are enforced before persistence",
        ),
        ("/api/v1/employees/{employee_id}", "get"): (
            EMPLOYEES_TAG,
            "Read tenant employee",
            "same not-found envelope as missing records",
        ),
        ("/api/v1/employees/{employee_id}", "patch"): (
            EMPLOYEES_TAG,
            "Update tenant employee",
            "employee number uniqueness",
        ),
        ("/api/v1/employees/{employee_id}", "delete"): (
            EMPLOYEES_TAG,
            "Archive tenant employee",
            "Employee IDs from other tenants return the same not-found envelope",
        ),
        ("/api/v1/employees/{employee_id}/leave-balances", "get"): (
            LEAVE_BALANCES_TAG,
            "List employee leave balance summaries",
            "read-only placeholder does not calculate accruals",
        ),
        ("/api/v1/leave-requests", "get"): (
            LEAVE_REQUESTS_TAG,
            "List tenant leave requests",
            "tenant isolation is applied before bounded keyset pagination",
        ),
        ("/api/v1/leave-requests", "post"): (
            LEAVE_REQUESTS_TAG,
            "Create tenant leave request",
            "ordered before persistence",
        ),
        ("/api/v1/leave-requests/{leave_request_id}/approve", "post"): (
            LEAVE_REQUESTS_TAG,
            "Approve pending leave request",
            "same not-found envelope as missing records",
        ),
        ("/api/v1/leave-requests/{leave_request_id}/reject", "post"): (
            LEAVE_REQUESTS_TAG,
            "Reject pending leave request",
            "same not-found envelope as missing records",
        ),
        ("/api/v1/leave-requests/{leave_request_id}/cancel", "post"): (
            LEAVE_REQUESTS_TAG,
            "Cancel pending leave request",
            "same not-found envelope as missing records",
        ),
    }

    for (path, method), (tag, summary, description_fragment) in expected_metadata.items():
        operation = paths[path][method]
        assert operation["tags"] == [tag]
        assert operation["summary"] == summary
        assert description_fragment in operation["description"]


def test_current_operations_use_tag_catalog_and_doc_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    allowed_tags = {tag["name"] for tag in OPENAPI_TAGS}
    for operations in openapi["paths"].values():
        for method, operation in operations.items():
            if method not in HTTP_METHODS:
                continue
            assert len(operation["tags"]) == 1
            assert operation["tags"][0] in allowed_tags
            assert operation["summary"].strip()
            assert operation["description"].strip()
            for response_metadata in operation["responses"].values():
                assert response_metadata["description"].strip()


def test_phase1_tenant_operations_document_injected_principal_denial() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_denials = {
        **{
            operation: (
                "Platform principal authorization denial envelope.",
                "platform_access_denied",
                "A valid platform access credential is required",
            )
            for operation in PLATFORM_TENANT_OPERATIONS
        },
        **{
            operation: (
                "Tenant principal authorization denial envelope.",
                "tenant_access_denied",
                "Tenant access requires a trusted principal",
            )
            for operation in TENANT_PRINCIPAL_OPERATIONS
        },
    }
    expected_principals = {
        **{operation: "platform" for operation in PLATFORM_TENANT_OPERATIONS},
        **{operation: "tenant" for operation in TENANT_PRINCIPAL_OPERATIONS},
    }

    for (path, method), (description, code, message) in expected_denials.items():
        operation = paths[path][method]
        denial = operation["responses"]["403"]
        media_type = denial["content"]["application/json"]

        # P3D retains the explicit principal metadata while wiring the production platform
        # audience instead of accepting a tenant credential or caller identity header.
        assert operation["x-required-principal"] == expected_principals[(path, method)]
        if expected_principals[(path, method)] == "platform":
            assert operation["security"] == [{"PlatformBearerAuth": []}]
        else:
            assert "security" not in operation
        assert denial["description"] == description
        assert media_type["schema"]["$ref"].endswith("/ApiErrorResponse")
        assert media_type["example"]["error"] == {
            "code": code,
            "message": message,
            "correlation_id": "req_wf_demo_001",
        }

    # Tenant and platform bearer schemes remain distinct in the generated contract.
    assert response.json()["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "description": "Short-lived access credential returned by the login endpoint.",
        "scheme": "bearer",
    }
    assert response.json()["components"]["securitySchemes"]["PlatformBearerAuth"] == {
        "type": "http",
        "description": "Short-lived credential issued only by the platform authentication realm.",
        "scheme": "bearer",
    }
    assert paths["/api/v1/users/invitations"]["post"]["security"] == [
        {"BearerAuth": []}
    ]


def test_phase1_tenant_operations_document_lifecycle_and_resource_errors() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_error_codes = {
        ("/api/v1/platform/tenants", "post"): {
            "409": {"tenant_slug_conflict"},
        },
        ("/api/v1/platform/tenants/{tenant_id}", "get"): {
            "404": {"tenant_not_found"},
        },
        ("/api/v1/platform/tenants/{tenant_id}", "patch"): {
            "404": {"tenant_not_found"},
            "409": {"tenant_lifecycle_conflict"},
        },
        ("/api/v1/platform/tenants/{tenant_id}/features", "get"): {
            "404": {"tenant_not_found"},
        },
        ("/api/v1/platform/tenants/{tenant_id}/features", "patch"): {
            "404": {"tenant_not_found"},
            "409": {"tenant_lifecycle_conflict"},
        },
        ("/api/v1/tenant", "get"): {
            "404": {"tenant_not_found"},
            "410": {"tenant_closed"},
            "423": {"tenant_not_ready"},
        },
        ("/api/v1/tenant/features", "get"): {
            "404": {"tenant_not_found"},
            "410": {"tenant_closed"},
            "423": {"tenant_not_ready"},
        },
        ("/api/v1/tenant/settings", "get"): {
            "404": {"tenant_not_found"},
            "410": {"tenant_closed"},
            "423": {"tenant_not_ready"},
        },
        ("/api/v1/tenant/settings", "patch"): {
            "404": {"tenant_not_found"},
            "410": {"tenant_closed"},
            "423": {"tenant_not_ready", "tenant_read_only"},
        },
    }

    for (path, method), responses in expected_error_codes.items():
        operation_responses = paths[path][method]["responses"]
        for status_code, error_codes in responses.items():
            documented = operation_responses[status_code]
            media_type = documented["content"]["application/json"]

            assert documented["description"].strip()
            assert media_type["schema"]["$ref"].endswith("/ApiErrorResponse")
            assert _documented_error_codes(media_type) == error_codes


def test_platform_tenant_operations_do_not_accept_caller_identity_headers() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    for path, method in PLATFORM_TENANT_OPERATIONS:
        parameters = paths[path][method].get("parameters", [])
        assert [parameter for parameter in parameters if parameter["in"] == "header"] == []


def test_platform_and_feature_response_schemas_cannot_reference_hr_schemas() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    schemas = openapi["components"]["schemas"]
    for path, method in PLATFORM_TENANT_OPERATIONS | FEATURE_OPERATIONS:
        references = _transitive_schema_references(
            openapi["paths"][path][method]["responses"],
            schemas,
        )
        assert not {
            reference
            for reference in references
            if reference.startswith(("Document", "Employee", "User", "Leave"))
        }


def test_phase1_operations_use_standard_envelopes_and_correlation_headers() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    schemas = openapi["components"]["schemas"]
    success_statuses = {
        ("/api/v1/platform/tenants", "post"): "201",
        ("/api/v1/platform/tenants", "get"): "200",
        ("/api/v1/platform/tenants/{tenant_id}", "get"): "200",
        ("/api/v1/platform/tenants/{tenant_id}", "patch"): "200",
        ("/api/v1/platform/tenants/{tenant_id}/features", "get"): "200",
        ("/api/v1/platform/tenants/{tenant_id}/features", "patch"): "200",
        ("/api/v1/tenant", "get"): "200",
        ("/api/v1/tenant/features", "get"): "200",
        ("/api/v1/tenant/settings", "get"): "200",
        ("/api/v1/tenant/settings", "patch"): "200",
    }
    for (path, method), status_code in success_statuses.items():
        success = openapi["paths"][path][method]["responses"][status_code]
        assert set(success["headers"]) == {
            "X-Correlation-Id",
            "X-Request-Id",
            "X-Trace-Id",
        }
        references = _transitive_schema_references(success, schemas)
        assert references & {"PageMeta", "ResponseMeta"}
        assert any(
            reference.startswith(("DataEnvelope", "ListEnvelope"))
            for reference in references
        )

    for path, method in PLATFORM_TENANT_OPERATIONS | TENANT_PRINCIPAL_OPERATIONS:
        responses = openapi["paths"][path][method]["responses"]
        assert "500" in responses
        for documented in responses.values():
            assert set(documented["headers"]) == {
                "X-Correlation-Id",
                "X-Request-Id",
                "X-Trace-Id",
            }


def test_feature_operations_document_project_validation_error_envelopes() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    for path, method in FEATURE_OPERATIONS:
        validation = paths[path][method]["responses"]["422"]
        schema_ref = validation["content"]["application/json"]["schema"]["$ref"]
        assert validation["description"].strip()
        assert schema_ref.endswith("/ApiErrorResponse")
        assert not schema_ref.endswith("/HTTPValidationError")


def test_feature_flag_openapi_schemas_are_finite_strict_and_tenant_safe() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert schemas["FeatureFlagKey"]["enum"] == [
        "organization",
        "employees",
        "documents",
        "leave",
        "self_service",
        "reporting",
        "notifications",
    ]

    update = schemas["TenantFeaturesUpdate"]
    assert update["additionalProperties"] is False
    assert set(update["properties"]) == {"features"}
    assert update["required"] == ["features"]
    assert update["properties"]["features"]["minItems"] == 1
    assert update["properties"]["features"]["maxItems"] == 7
    assert update["properties"]["features"]["items"]["$ref"].endswith(
        "/TenantFeatureFlagUpdate"
    )

    update_item = schemas["TenantFeatureFlagUpdate"]
    assert update_item["additionalProperties"] is False
    assert set(update_item["properties"]) == {"key", "enabled"}
    assert set(update_item["required"]) == {"key", "enabled"}
    assert update_item["properties"]["key"]["$ref"].endswith("/FeatureFlagKey")
    assert update_item["properties"]["enabled"]["type"] == "boolean"

    read_item = schemas["TenantFeatureFlagRead"]
    assert set(read_item["properties"]) == {"key", "enabled", "source"}
    assert set(read_item["required"]) == {"key", "enabled", "source"}
    assert read_item["properties"]["source"]["enum"] == ["default", "override"]


def test_platform_tenant_schema_exposes_configured_limits_without_usage_fields() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    platform_read = schemas["TenantPlatformRead"]
    assert platform_read["properties"]["limits"]["$ref"].endswith("/TenantLimitsRead")
    assert "limits" in platform_read["required"]

    limits = schemas["TenantLimitsRead"]
    assert set(limits["properties"]) == {"active_employees"}
    assert limits["required"] == ["active_employees"]
    assert "not an HR-derived usage counter" in limits["description"]
    variants = limits["properties"]["active_employees"]["anyOf"]
    integer_schema = next(item for item in variants if item.get("type") == "integer")
    assert integer_schema["minimum"] == 1
    assert integer_schema["maximum"] == 1_000_000
    assert {item.get("type") for item in variants} == {"integer", "null"}

    for forbidden_field in {
        "employee_count",
        "used",
        "remaining",
        "usage",
        "employees",
    }:
        assert forbidden_field not in limits["properties"]


def test_platform_tenant_list_documents_cursor_only_bounded_page_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/platform/tenants"]["get"]
    params = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert set(params) == {"cursor", "limit"}
    limit_schema = params["limit"]["schema"]
    assert limit_schema["default"] == TENANT_LIST_DEFAULT_LIMIT
    assert limit_schema["maximum"] == TENANT_LIST_MAX_LIMIT
    assert limit_schema["minimum"] == 1
    assert limit_schema["type"] == "integer"
    assert "opaque" in params["cursor"]["description"].lower()
    assert "created_at" in operation["description"]
    assert "offset" not in operation["description"].lower()


def test_phase0_list_response_and_offset_deprecation_contracts_remain_explicit() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in ("/api/v1/employees", "/api/v1/leave-requests"):
        operation = paths[path]["get"]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        parameters = {item["name"]: item for item in operation["parameters"]}
        assert schema["type"] == "array"
        assert "data" not in schema
        assert parameters["offset"]["deprecated"] is True
        assert "compatibility" in parameters["offset"]["description"].lower()
        assert "X-Next-Cursor" in operation["responses"]["200"]["headers"]


def test_leave_balance_placeholder_openapi_surface_is_read_only() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    leave_balance_path = "/api/v1/employees/{employee_id}/leave-balances"
    assert set(paths[leave_balance_path]) == {"get"}
    params = {
        parameter["name"]: parameter for parameter in paths[leave_balance_path]["get"]["parameters"]
    }
    assert "single period year" in params["period_year"]["description"]

    mutating_methods = {"post", "put", "patch", "delete"}
    tagged_mutations = [
        (path, method)
        for path, operations in paths.items()
        for method, operation in operations.items()
        if method in mutating_methods and operation["tags"] == [LEAVE_BALANCES_TAG]
    ]
    assert tagged_mutations == []


def test_domain_operations_document_required_tenant_headers() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    protected_operations = {
        ("/api/v1/dashboard/summary", "get"),
        ("/api/v1/employees", "get"),
        ("/api/v1/employees", "post"),
        ("/api/v1/employees/{employee_id}", "get"),
        ("/api/v1/employees/{employee_id}", "patch"),
        ("/api/v1/employees/{employee_id}", "delete"),
        ("/api/v1/employees/{employee_id}/leave-balances", "get"),
        ("/api/v1/leave-requests", "get"),
        ("/api/v1/leave-requests", "post"),
        ("/api/v1/leave-requests/{leave_request_id}/approve", "post"),
        ("/api/v1/leave-requests/{leave_request_id}/reject", "post"),
        ("/api/v1/leave-requests/{leave_request_id}/cancel", "post"),
    }
    for path, method in protected_operations:
        params = {parameter["name"]: parameter for parameter in paths[path][method]["parameters"]}
        tenant_id_header = params[TENANT_ID_HEADER]
        tenant_slug_header = params[TENANT_SLUG_HEADER]

        assert tenant_id_header["in"] == "header"
        assert tenant_id_header["required"] is True
        assert "single canonical hyphenated UUID" in tenant_id_header["description"]
        assert tenant_slug_header["in"] == "header"
        assert tenant_slug_header["required"] is False
        assert "non-empty when provided" in tenant_slug_header["description"]


def test_employee_list_openapi_documents_filter_query_params() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/employees"]["get"]
    params = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert {"department", "status", "q", "limit", "offset", "cursor"}.issubset(params)
    assert params["department"]["in"] == "query"
    assert "exact department value within the tenant" in params["department"]["description"]
    assert params["status"]["in"] == "query"
    assert "employment lifecycle status" in params["status"]["description"]
    assert params["q"]["in"] == "query"
    assert "within the tenant" in params["q"]["description"]
    assert params["limit"]["schema"]["default"] == EMPLOYEE_LIST_DEFAULT_LIMIT
    assert params["limit"]["schema"]["maximum"] == EMPLOYEE_LIST_MAX_LIMIT
    assert params["limit"]["schema"]["minimum"] == 1
    assert params["offset"]["schema"]["default"] == 0
    assert params["offset"]["schema"]["minimum"] == 0
    assert params["offset"]["deprecated"] is True
    assert "opaque keyset cursor" in params["cursor"]["description"]
    next_cursor_header = operation["responses"]["200"]["headers"]["X-Next-Cursor"]
    assert "next deterministic page" in next_cursor_header["description"]


def test_leave_request_list_openapi_documents_filter_query_params() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/leave-requests"]["get"]
    params = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert {
        "status",
        "employee_id",
        "start_date",
        "end_date",
        "limit",
        "offset",
        "cursor",
    }.issubset(params)
    assert params["status"]["in"] == "query"
    assert "leave request workflow status" in params["status"]["description"]
    assert params["employee_id"]["in"] == "query"
    assert "one employee in the current tenant" in params["employee_id"]["description"]
    assert params["start_date"]["in"] == "query"
    assert "Inclusive start" in params["start_date"]["description"]
    assert params["end_date"]["in"] == "query"
    assert "Inclusive end" in params["end_date"]["description"]
    assert params["limit"]["schema"]["default"] == LEAVE_REQUEST_LIST_DEFAULT_LIMIT
    assert params["limit"]["schema"]["maximum"] == LEAVE_REQUEST_LIST_MAX_LIMIT
    assert params["limit"]["schema"]["minimum"] == 1
    assert params["offset"]["schema"]["default"] == 0
    assert params["offset"]["schema"]["minimum"] == 0
    assert params["offset"]["deprecated"] is True
    assert "opaque keyset cursor" in params["cursor"]["description"]
    next_cursor_header = operation["responses"]["200"]["headers"]["X-Next-Cursor"]
    assert "next deterministic page" in next_cursor_header["description"]


def test_employee_and_leave_openapi_document_project_error_envelope_for_422() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    operations = {
        ("/api/v1/employees", "post"): "Employee endpoint validation error envelope.",
        (
            "/api/v1/employees/{employee_id}/leave-balances",
            "get",
        ): "Leave balance endpoint validation error envelope.",
        ("/api/v1/leave-requests", "post"): "Leave request endpoint validation error envelope.",
    }
    for (path, method), description in operations.items():
        response_422 = paths[path][method]["responses"]["422"]
        schema_ref = response_422["content"]["application/json"]["schema"]["$ref"]
        assert response_422["description"] == description
        assert schema_ref.endswith("/ApiErrorResponse")
        assert not schema_ref.endswith("/HTTPValidationError")


def test_employee_and_leave_commands_document_stable_conflict_envelopes() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    operations = {
        ("/api/v1/employees", "post"): {
            "employee_number_conflict",
            "data_integrity_conflict",
            "concurrent_write_conflict",
            "idempotency_key_mismatch",
        },
        ("/api/v1/employees/{employee_id}", "patch"): {
            "employee_number_conflict",
            "data_integrity_conflict",
            "concurrent_write_conflict",
        },
        ("/api/v1/leave-requests/{leave_request_id}/approve", "post"): {
            "leave_request_transition_conflict",
            "data_integrity_conflict",
            "concurrent_write_conflict",
            "idempotency_key_mismatch",
        },
        ("/api/v1/leave-requests", "post"): {
            "data_integrity_conflict",
            "concurrent_write_conflict",
            "idempotency_key_mismatch",
        },
        ("/api/v1/leave-requests/{leave_request_id}/reject", "post"): {
            "leave_request_transition_conflict",
            "data_integrity_conflict",
            "concurrent_write_conflict",
            "idempotency_key_mismatch",
        },
        ("/api/v1/leave-requests/{leave_request_id}/cancel", "post"): {
            "leave_request_transition_conflict",
            "data_integrity_conflict",
            "concurrent_write_conflict",
            "idempotency_key_mismatch",
        },
    }
    for (path, method), expected_examples in operations.items():
        response_409 = paths[path][method]["responses"]["409"]
        media_type = response_409["content"]["application/json"]
        assert "command" in response_409["description"]
        assert response_409["description"].endswith("conflict envelope.")
        assert media_type["schema"]["$ref"].endswith("/ApiErrorResponse")
        assert set(media_type["examples"]) == expected_examples


def test_critical_post_commands_document_optional_tenant_scoped_idempotency_key() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    idempotent_operations = [
        ("/api/v1/employees", "post"),
        ("/api/v1/leave-requests", "post"),
        ("/api/v1/leave-requests/{leave_request_id}/approve", "post"),
        ("/api/v1/leave-requests/{leave_request_id}/reject", "post"),
        ("/api/v1/leave-requests/{leave_request_id}/cancel", "post"),
    ]
    for path, method in idempotent_operations:
        operation = paths[path][method]
        header = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "X-Idempotency-Key"
        )
        assert header["in"] == "header"
        assert header["required"] is False
        assert "tenant-scoped retry key" in header["description"]
        response_400 = operation["responses"]["400"]
        media_type = response_400["content"]["application/json"]
        assert response_400["description"] == (
            "Idempotency key validation error envelope."
        )
        assert media_type["schema"]["$ref"].endswith("/ApiErrorResponse")
        assert set(media_type["examples"]) == {"idempotency_key_invalid"}

    patch_headers = {
        parameter["name"]
        for parameter in paths["/api/v1/employees/{employee_id}"]["patch"]["parameters"]
    }
    assert "X-Idempotency-Key" not in patch_headers


def test_p3b_login_contract_is_email_first_and_discriminates_safe_outcomes() -> None:
    openapi = create_app().openapi()
    schemas = openapi["components"]["schemas"]
    login_request = schemas["LoginRequest"]

    assert set(login_request["properties"]) == {"email", "password"}
    assert set(login_request["required"]) == {"email", "password"}
    assert login_request["additionalProperties"] is False

    login_operation = openapi["paths"]["/api/v1/auth/login"]["post"]
    assert "429" in login_operation["responses"]
    assert "Retry-After" in login_operation["responses"]["429"]["headers"]
    selection = schemas["OrganizationSelectionRead"]
    assert set(selection["properties"]) == {
        "status",
        "selection_transaction",
        "expires_in",
        "organizations",
    }
    assert set(schemas["OrganizationChoiceRead"]["properties"]) == {
        "selection_key",
        "display_name",
    }


def _transitive_schema_references(
    value: object,
    schemas: dict[str, object],
) -> set[str]:
    references = _schema_references(value)
    pending = list(references)
    while pending:
        reference = pending.pop()
        component = schemas.get(reference)
        if component is None:
            continue
        discovered = _schema_references(component) - references
        references.update(discovered)
        pending.extend(discovered)
    return references


def _schema_references(value: object) -> set[str]:
    if isinstance(value, dict):
        references = {
            candidate.rsplit("/", maxsplit=1)[-1]
            for key, candidate in value.items()
            if key == "$ref" and isinstance(candidate, str)
        }
        for nested in value.values():
            references.update(_schema_references(nested))
        return references
    if isinstance(value, list):
        return {
            reference
            for nested in value
            for reference in _schema_references(nested)
        }
    return set()


def _documented_error_codes(media_type: dict[str, object]) -> set[str]:
    if "example" in media_type:
        examples = [media_type["example"]]
    else:
        examples = [
            example["value"]
            for example in media_type["examples"].values()
        ]
    return {example["error"]["code"] for example in examples}
