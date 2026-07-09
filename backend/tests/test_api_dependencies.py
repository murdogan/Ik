from typing import Annotated
from uuid import UUID

import pytest
from app.api.dependencies import get_tenant_context
from app.api.errors import ApiError, api_error_handler, request_validation_error_handler
from app.core.tenancy import TenantContext
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

TENANT_ID = UUID("11111111-aaaa-4111-8111-111111111111")


def _client() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)

    @app.get("/tenant-context")
    def tenant_context(
        context: Annotated[TenantContext, Depends(get_tenant_context)],
    ) -> dict[str, str]:
        return {"tenant_id": str(context.tenant_id), "slug": context.slug}

    return TestClient(app)


def _assert_error_response(
    response,
    *,
    status_code: int,
    code: str,
    message: str,
    correlation_id: str | None = None,
) -> None:
    assert response.status_code == status_code
    assert response.json() == {
        "error": {
            "code": code,
            "message": message,
            "details": None,
            "correlation_id": correlation_id,
        }
    }


def test_tenant_dependency_accepts_valid_tenant_header() -> None:
    response = _client().get(
        "/tenant-context",
        headers={
            "X-Tenant-Id": f" {str(TENANT_ID).upper()} ",
            "X-Tenant-Slug": " wealthy-falcon ",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": str(TENANT_ID),
        "slug": "wealthy-falcon",
    }


def test_tenant_dependency_uses_tenant_id_as_default_slug() -> None:
    response = _client().get("/tenant-context", headers={"X-Tenant-Id": str(TENANT_ID)})

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": str(TENANT_ID),
        "slug": str(TENANT_ID),
    }


def test_tenant_dependency_rejects_missing_tenant_header() -> None:
    response = _client().get(
        "/tenant-context",
        headers={"X-Correlation-Id": "tenant-missing"},
    )

    _assert_error_response(
        response,
        status_code=400,
        code="tenant_header_missing",
        message="X-Tenant-Id header is required",
        correlation_id="tenant-missing",
    )


def test_tenant_dependency_rejects_blank_tenant_header() -> None:
    response = _client().get(
        "/tenant-context",
        headers={"X-Tenant-Id": " ", "X-Correlation-Id": "tenant-blank"},
    )

    _assert_error_response(
        response,
        status_code=400,
        code="tenant_header_missing",
        message="X-Tenant-Id header is required",
        correlation_id="tenant-blank",
    )


@pytest.mark.parametrize(
    "tenant_header",
    [
        "not-a-uuid",
        str(TENANT_ID).replace("-", ""),
        f"{{{TENANT_ID}}}",
        f"urn:uuid:{TENANT_ID}",
    ],
)
def test_tenant_dependency_rejects_invalid_tenant_header(tenant_header: str) -> None:
    response = _client().get(
        "/tenant-context",
        headers={"X-Tenant-Id": tenant_header, "X-Correlation-Id": "tenant-invalid"},
    )

    _assert_error_response(
        response,
        status_code=400,
        code="tenant_header_invalid",
        message="X-Tenant-Id header must be a valid UUID",
        correlation_id="tenant-invalid",
    )


def test_tenant_dependency_rejects_repeated_tenant_header() -> None:
    response = _client().get(
        "/tenant-context",
        headers=[
            ("X-Tenant-Id", str(TENANT_ID)),
            ("X-Tenant-Id", "22222222-bbbb-4222-8222-222222222222"),
            ("X-Correlation-Id", "tenant-repeated"),
        ],
    )

    _assert_error_response(
        response,
        status_code=400,
        code="tenant_header_invalid",
        message="X-Tenant-Id header must be a valid UUID",
        correlation_id="tenant-repeated",
    )


def test_tenant_dependency_rejects_blank_tenant_slug_header() -> None:
    response = _client().get(
        "/tenant-context",
        headers={
            "X-Tenant-Id": str(TENANT_ID),
            "X-Tenant-Slug": " ",
            "X-Correlation-Id": "tenant-slug-blank",
        },
    )

    _assert_error_response(
        response,
        status_code=400,
        code="tenant_slug_header_invalid",
        message="X-Tenant-Slug header must be non-empty when provided",
        correlation_id="tenant-slug-blank",
    )


def test_tenant_dependency_rejects_repeated_tenant_slug_header() -> None:
    response = _client().get(
        "/tenant-context",
        headers=[
            ("X-Tenant-Id", str(TENANT_ID)),
            ("X-Tenant-Slug", "wealthy-falcon"),
            ("X-Tenant-Slug", "other-falcon"),
            ("X-Correlation-Id", "tenant-slug-repeated"),
        ],
    )

    _assert_error_response(
        response,
        status_code=400,
        code="tenant_slug_header_invalid",
        message="X-Tenant-Slug header must be non-empty when provided",
        correlation_id="tenant-slug-repeated",
    )
