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
            "Public operational endpoints for API health, uptime, and platform readiness checks."
        ),
    },
    {
        "name": PUBLIC_TAG,
        "description": (
            "Public Wealthy Falcon HR browser endpoints exposed outside tenant-scoped APIs."
        ),
    },
    {
        "name": DASHBOARD_TAG,
        "description": (
            "Tenant-scoped HR operating metrics for executive and people-team dashboard views."
        ),
    },
    {
        "name": EMPLOYEES_TAG,
        "description": (
            "Tenant-scoped employee master data, profile lookup, and employment lifecycle "
            "operations."
        ),
    },
    {
        "name": LEAVE_BALANCES_TAG,
        "description": (
            "Tenant-scoped read-only manual leave balance summaries with no accrual engine or "
            "external integrations."
        ),
    },
    {
        "name": LEAVE_REQUESTS_TAG,
        "description": (
            "Tenant-scoped leave request listing, creation, and pending-request decision "
            "workflow endpoints."
        ),
    },
]
