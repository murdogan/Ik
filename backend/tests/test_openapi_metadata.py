from app.api.errors import TENANT_ID_HEADER, TENANT_SLUG_HEADER
from app.api.openapi import (
    DASHBOARD_TAG,
    EMPLOYEES_TAG,
    LEAVE_BALANCES_TAG,
    LEAVE_REQUESTS_TAG,
    OPENAPI_TAGS,
    PUBLIC_TAG,
    SYSTEM_TAG,
)
from app.main import create_app
from fastapi.testclient import TestClient

HTTP_METHODS = {"delete", "get", "patch", "post", "put"}


def test_openapi_uses_readable_tag_catalog() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["tags"] == OPENAPI_TAGS
    descriptions = {tag["name"]: tag["description"] for tag in response.json()["tags"]}
    assert "API health" in descriptions[SYSTEM_TAG]
    assert "outside tenant-scoped APIs" in descriptions[PUBLIC_TAG]
    assert "dashboard views" in descriptions[DASHBOARD_TAG]
    assert "profile lookup" in descriptions[EMPLOYEES_TAG]
    assert "no accrual engine" in descriptions[LEAVE_BALANCES_TAG]
    assert "pending-request decision workflow" in descriptions[LEAVE_REQUESTS_TAG]


def test_current_operations_have_readable_openapi_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_metadata = {
        ("/health", "get"): (
            SYSTEM_TAG,
            "Check API health",
            "public Wealthy Falcon HR API status metadata",
        ),
        ("/", "get"): (
            PUBLIC_TAG,
            "Serve Wealthy Falcon HR landing",
            "landing page HTML for browser requests",
        ),
        ("/api/v1/dashboard/summary", "get"): (
            DASHBOARD_TAG,
            "Read tenant dashboard summary",
            "tenant header context",
        ),
        ("/api/v1/employees", "get"): (
            EMPLOYEES_TAG,
            "List tenant employees",
            "bounded limit/offset pagination",
        ),
        ("/api/v1/employees", "post"): (
            EMPLOYEES_TAG,
            "Create tenant employee",
            "lifecycle date rules are enforced",
        ),
        ("/api/v1/employees/{employee_id}", "get"): (
            EMPLOYEES_TAG,
            "Read tenant employee",
            "Employees from other tenants are treated as not found",
        ),
        ("/api/v1/employees/{employee_id}", "patch"): (
            EMPLOYEES_TAG,
            "Update tenant employee",
            "employment lifecycle date rules",
        ),
        ("/api/v1/employees/{employee_id}", "delete"): (
            EMPLOYEES_TAG,
            "Delete tenant employee",
            "Employees from other tenants are treated as not found",
        ),
        ("/api/v1/employees/{employee_id}/leave-balances", "get"): (
            LEAVE_BALANCES_TAG,
            "List employee leave balance summaries",
            "reads stored summaries only",
        ),
        ("/api/v1/leave-requests", "get"): (
            LEAVE_REQUESTS_TAG,
            "List tenant leave requests",
            "bounded limit/offset pagination",
        ),
        ("/api/v1/leave-requests", "post"): (
            LEAVE_REQUESTS_TAG,
            "Create tenant leave request",
            "leave dates must be ordered",
        ),
        ("/api/v1/leave-requests/{leave_request_id}/approve", "post"): (
            LEAVE_REQUESTS_TAG,
            "Approve tenant leave request",
            "Leave requests from other tenants are treated as not found",
        ),
        ("/api/v1/leave-requests/{leave_request_id}/reject", "post"): (
            LEAVE_REQUESTS_TAG,
            "Reject tenant leave request",
            "Leave requests from other tenants are treated as not found",
        ),
        ("/api/v1/leave-requests/{leave_request_id}/cancel", "post"): (
            LEAVE_REQUESTS_TAG,
            "Cancel tenant leave request",
            "Leave requests from other tenants are treated as not found",
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


def test_leave_balance_placeholder_openapi_surface_is_read_only() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    leave_balance_path = "/api/v1/employees/{employee_id}/leave-balances"
    assert set(paths[leave_balance_path]) == {"get"}

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

    assert {"department", "status", "q", "limit", "offset"}.issubset(params)
    assert params["department"]["in"] == "query"
    assert "exact department value within the tenant" in params["department"]["description"]
    assert params["status"]["in"] == "query"
    assert "employment lifecycle status" in params["status"]["description"]
    assert params["q"]["in"] == "query"
    assert "within the tenant" in params["q"]["description"]
    assert params["limit"]["schema"]["maximum"] == 200
    assert params["offset"]["schema"]["minimum"] == 0


def test_leave_request_list_openapi_documents_filter_query_params() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/leave-requests"]["get"]
    params = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert {"status", "employee_id", "start_date", "end_date", "limit", "offset"}.issubset(
        params
    )
    assert params["status"]["in"] == "query"
    assert "leave request workflow status" in params["status"]["description"]
    assert params["employee_id"]["in"] == "query"
    assert "one employee in the current tenant" in params["employee_id"]["description"]
    assert params["start_date"]["in"] == "query"
    assert "Inclusive start" in params["start_date"]["description"]
    assert params["end_date"]["in"] == "query"
    assert "Inclusive end" in params["end_date"]["description"]
    assert params["limit"]["schema"]["maximum"] == 200
    assert params["offset"]["schema"]["minimum"] == 0


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
