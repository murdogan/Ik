SYSTEM_TAG = "System"
PUBLIC_TAG = "Public"
DASHBOARD_TAG = "Dashboard"
EMPLOYEES_TAG = "Employees"
LEAVE_BALANCES_TAG = "Leave Balances"
LEAVE_REQUESTS_TAG = "Leave Requests"

OPENAPI_TAGS = [
    {
        "name": SYSTEM_TAG,
        "description": "Public operational endpoints for service health and availability checks.",
    },
    {
        "name": PUBLIC_TAG,
        "description": "Public Wealthy Falcon HR experience endpoints exposed outside tenant APIs.",
    },
    {
        "name": DASHBOARD_TAG,
        "description": (
            "Tenant-scoped HR operating metrics for executive and people-team dashboards."
        ),
    },
    {
        "name": EMPLOYEES_TAG,
        "description": "Tenant-scoped employee master data and employment lifecycle operations.",
    },
    {
        "name": LEAVE_BALANCES_TAG,
        "description": "Tenant-scoped read-only manual leave balance summary endpoints.",
    },
    {
        "name": LEAVE_REQUESTS_TAG,
        "description": (
            "Tenant-scoped leave request list, creation, and approval workflow endpoints."
        ),
    },
]
