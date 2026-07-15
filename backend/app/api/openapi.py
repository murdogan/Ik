from typing import Any

SYSTEM_TAG = "System"
PUBLIC_TAG = "Public"
AUTHENTICATION_TAG = "Authentication"
AUTHORIZATION_TAG = "Authorization"
AUDIT_TAG = "Audit"
PLATFORM_AUDIT_TAG = "Platform Audit"
USER_ADMINISTRATION_TAG = "User Administration"
ORGANIZATION_TAG = "Organization"
PLATFORM_TENANTS_TAG = "Platform Tenants"
TENANT_SETTINGS_TAG = "Tenant Settings"
DASHBOARD_TAG = "Dashboard"
EMPLOYEES_TAG = "Employees"
DOCUMENTS_TAG = "Employee Documents"
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
            "Email-first tenant login, post-credential organization selection, and activation "
            "plus cookie-backed refresh rotation, logout, and live-session current-user "
            "validation. Memberships are disclosed only after credential verification; the "
            "platform login realm and token audience remain separate from tenant sessions."
        ),
    },
    {
        "name": AUTHORIZATION_TAG,
        "description": (
            "Seeded deny-by-default role and permission catalogs for tenant administration. "
            "Platform roles are kept outside tenant assignment surfaces."
        ),
    },
    {
        "name": AUDIT_TAG,
        "description": (
            "Permission- and category-filtered append-only tenant security and administration "
            "history with redacted metadata and cursor pagination."
        ),
    },
    {
        "name": PLATFORM_AUDIT_TAG,
        "description": (
            "Platform-operations audit history kept separate from tenant security and HR data."
        ),
    },
    {
        "name": USER_ADMINISTRATION_TAG,
        "description": (
            "Authenticated tenant user listing, indexed search, account updates, and invitations. "
            "Tenant and actor scope come from a validated session-backed RequestContext and are "
            "never accepted from caller-supplied fields."
        ),
    },
    {
        "name": ORGANIZATION_TAG,
        "description": (
            "Authenticated tenant legal-entity, branch/location, department hierarchy, position, "
            "effective-dated assignment, team, and bounded org-chart administration with stable "
            "codes, terminal archive history, derived manager scope, and audited writes."
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
        "name": DOCUMENTS_TAG,
        "description": (
            "Tenant-scoped document policies, short-lived object grants, verified upload "
            "finalization, malware quarantine, HR checklists, and employee-safe own access."
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
