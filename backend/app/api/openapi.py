SYSTEM_TAG = "System"
PUBLIC_TAG = "Public"
PLATFORM_TENANTS_TAG = "Platform Tenants"
TENANT_SETTINGS_TAG = "Tenant Settings"
DASHBOARD_TAG = "Dashboard"
EMPLOYEES_TAG = "Employees"
LEAVE_BALANCES_TAG = "Leave Balances"
LEAVE_REQUESTS_TAG = "Leave Requests"

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
        "name": PLATFORM_TENANTS_TAG,
        "description": (
            "Default-deny platform provisioning and lifecycle metadata. Responses contain tenant "
            "plan, region, locale, timezone, and lifecycle-derived health only—never HR data."
        ),
    },
    {
        "name": TENANT_SETTINGS_TAG,
        "description": (
            "Trusted-principal tenant metadata and a fixed, typed settings allowlist with "
            "lifecycle-aware read and write behavior."
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
