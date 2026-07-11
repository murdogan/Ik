from typing import Any

SYSTEM_TAG = "System"
PUBLIC_TAG = "Public"
AUTHENTICATION_TAG = "Authentication"
USER_ADMINISTRATION_TAG = "User Administration"
PLATFORM_TENANTS_TAG = "Platform Tenants"
TENANT_SETTINGS_TAG = "Tenant Settings"
DASHBOARD_TAG = "Dashboard"
EMPLOYEES_TAG = "Employees"
LEAVE_BALANCES_TAG = "Leave Balances"
LEAVE_REQUESTS_TAG = "Leave Requests"

# Phase 1 has no caller-facing credential format: authorization is supplied only by the trusted
# principal dependency seam and fails closed by default.  A standard OpenAPI security scheme would
# falsely advertise bearer, API-key, or mutual-TLS behavior that is not implemented until Phase 2.
# This operation extension records the executable boundary without making that false claim.
PLATFORM_PRINCIPAL_OPENAPI = {"x-required-principal": "platform"}
TENANT_PRINCIPAL_OPENAPI = {"x-required-principal": "tenant"}

CORRELATION_RESPONSE_HEADERS = {
    "X-Request-Id": {
        "description": "Validated or server-generated opaque request identifier.",
        "schema": {"type": "string"},
    },
    "X-Trace-Id": {
        "description": "Validated or server-generated 32-character lowercase trace identifier.",
        "schema": {"type": "string", "minLength": 32, "maxLength": 32},
    },
    "X-Correlation-Id": {
        "description": "Deprecated compatibility alias of X-Request-Id.",
        "schema": {"type": "string", "deprecated": True},
    },
}


def with_correlation_response_headers(
    responses: dict[int | str, dict[str, Any]],
) -> dict[int | str, dict[str, Any]]:
    """Document the global safe headers without mutating shared response fixtures."""

    return {
        status_code: {
            **metadata,
            "headers": {
                **metadata.get("headers", {}),
                **CORRELATION_RESPONSE_HEADERS,
            },
        }
        for status_code, metadata in responses.items()
    }

OPENAPI_TAGS = [
    {
        "name": SYSTEM_TAG,
        "description": (
            "Public operational checks for service health, version, and environment readiness; "
            "these endpoints do not require tenant context."
        ),
    },
    {
        "name": PUBLIC_TAG,
        "description": (
            "Browser-facing Wealthy Falcon HR pages served outside the tenant-scoped JSON API."
        ),
    },
    {
        "name": AUTHENTICATION_TAG,
        "description": (
            "Tenant-aware login and activation plus cookie-backed refresh rotation, logout, and "
            "live-session current-user validation. Credential failures are generic and all "
            "credential-bearing responses are non-cacheable."
        ),
    },
    {
        "name": USER_ADMINISTRATION_TAG,
        "description": (
            "Authenticated tenant user invitations. Tenant and actor scope come from a signed "
            "credential and are never accepted from caller-supplied tenant fields."
        ),
    },
    {
        "name": PLATFORM_TENANTS_TAG,
        "description": (
            "Default-deny platform provisioning and lifecycle metadata. Responses contain tenant "
            "plan, configured limits, region, locale, timezone, lifecycle-derived health, and "
            "allowlisted rollout flags only—never HR data or HR-derived usage counts."
        ),
    },
    {
        "name": TENANT_SETTINGS_TAG,
        "description": (
            "Trusted-principal tenant metadata, a fixed typed settings allowlist, and read-only "
            "effective module flags with lifecycle-aware behavior."
        ),
    },
    {
        "name": DASHBOARD_TAG,
        "description": (
            "Tenant-scoped HR dashboard metrics for workforce counts, leave workload, department "
            "distribution, new starters, and recent activity."
        ),
    },
    {
        "name": EMPLOYEES_TAG,
        "description": (
            "Tenant-scoped employee master data for directory search, profile lookup, lifecycle "
            "status, and record changes."
        ),
    },
    {
        "name": LEAVE_BALANCES_TAG,
        "description": (
            "Tenant-scoped read-only manual leave balance summaries for HR review; no accrual "
            "engine or external integrations are exposed."
        ),
    },
    {
        "name": LEAVE_REQUESTS_TAG,
        "description": (
            "Tenant-scoped leave request intake, filtered review queues, and pending-request "
            "approve, reject, or cancel decisions."
        ),
    },
]
