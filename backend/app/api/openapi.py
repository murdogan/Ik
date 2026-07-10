SYSTEM_TAG = "System"
PUBLIC_TAG = "Public"
DASHBOARD_TAG = "Dashboard"
EMPLOYEES_TAG = "Employees"
LEAVE_BALANCES_TAG = "Leave Balances"
LEAVE_REQUESTS_TAG = "Leave Requests"

OPENAPI_TAGS = [
    {
        "name": SYSTEM_TAG,
        "description": (
            "Public operational endpoints for API health and platform readiness checks."
        ),
    },
    {
        "name": PUBLIC_TAG,
        "description": (
            "Browser-facing public pages exposed outside tenant-scoped Wealthy Falcon HR APIs."
        ),
    },
    {
        "name": DASHBOARD_TAG,
        "description": (
            "Tenant-scoped HR dashboard metrics for workforce counts, leave workload, and "
            "recent activity."
        ),
    },
    {
        "name": EMPLOYEES_TAG,
        "description": (
            "Tenant-scoped employee directory, profile lookup, lifecycle status, and record "
            "management."
        ),
    },
    {
        "name": LEAVE_BALANCES_TAG,
        "description": (
            "Tenant-scoped read-only manual leave balance summaries; no accrual engine or "
            "external integrations are exposed."
        ),
    },
    {
        "name": LEAVE_REQUESTS_TAG,
        "description": (
            "Tenant-scoped leave request intake, filtering, and pending-request decision "
            "workflow."
        ),
    },
]
