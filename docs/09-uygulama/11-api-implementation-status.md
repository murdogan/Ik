# API Implementation Status Report

Date: 2026-07-10
Branch: `codex/continuous-24h-backend`
Task: `W3C5 OpenAPI tag hygiene`

## Scope

- Refined the OpenAPI tag catalog descriptions while keeping the existing tag names stable:
  `System`, `Public`, `Dashboard`, `Employees`, `Leave Balances`, and `Leave Requests`.
- Reworded current route summaries, operation descriptions, and response descriptions for clearer
  tenant-aware API docs.
- Extended OpenAPI metadata regression coverage for the refreshed copy and leave balance
  `period_year` parameter description.
- No production/staging deploy, cron, token, auth, credential, `.env`, UI, payroll/bordro, SGK,
  banks, PDKS, AI, or external integration changes.
- No runtime API behavior, request/response payload shape, model, migration, or tenant isolation
  change.

## Completed API Surface

| Method | Path | Status | Smoke coverage |
|---|---|---|---|
| GET | `/health` | Implemented | Health response and documented OpenAPI operation |
| GET | `/` | Implemented | Wealthy Falcon HR landing response and documented OpenAPI operation |
| GET | `/openapi.json` | Implemented by FastAPI | Generated schema fetch and documented operation drift check |
| GET | `/api/v1/dashboard/summary` | Implemented | Tenant-scoped enriched metrics and documented OpenAPI operation |
| GET | `/api/v1/employees` | Implemented | Tenant list, filters, pagination, and documented OpenAPI operation |
| POST | `/api/v1/employees` | Implemented | Tenant create, duplicate protection, and documented OpenAPI operation |
| GET | `/api/v1/employees/{employee_id}` | Implemented | Detail, tenant isolation, and documented OpenAPI operation |
| PATCH | `/api/v1/employees/{employee_id}` | Implemented | Partial update, lifecycle rules, and documented OpenAPI operation |
| DELETE | `/api/v1/employees/{employee_id}` | Implemented | Delete, not-found check, and documented OpenAPI operation |
| GET | `/api/v1/employees/{employee_id}/leave-balances` | Implemented | Manual summaries, period filter, tenant isolation, and documented OpenAPI operation |
| GET | `/api/v1/leave-requests` | Implemented | Tenant list, filters, pagination, and documented OpenAPI operation |
| POST | `/api/v1/leave-requests` | Implemented | Pending create, tenant checks, and documented OpenAPI operation |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | Implemented | Pending-only transition, tenant checks, and documented OpenAPI operation |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | Implemented | Pending-only transition and documented OpenAPI operation |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | Implemented | Pending-only transition and documented OpenAPI operation |

## Current Behavior Notes

- Domain endpoints require exactly one canonical hyphenated UUID `X-Tenant-Id`; `X-Tenant-Slug`
  remains optional but cannot be blank or repeated when sent.
- Employee list supports `department`, `status`, `q`, `limit`, and `offset`. Filters are scoped to
  the current tenant before pagination.
- Employee lifecycle validation is active: `terminated` requires `employment_end_date`; `active`
  and `on_leave` require `employment_end_date: null`. Violations return
  `employee_invalid_lifecycle`, and the database also has
  `ck_employees_lifecycle_status_dates`.
- Leave request list supports `status`, `employee_id`, inclusive overlapping `start_date` and
  `end_date` filters, plus bounded `limit` and `offset` pagination. Ordering is deterministic by
  `created_at desc`, `start_date asc`, and `id asc`.
- Dashboard summary is DB-backed and tenant-scoped. It returns active employee count, workforce
  count, pending leave count, new starters this month, department distribution, recent activity,
  and compatibility fields currently used by the frontend-facing contract.
- Leave balance summaries are read-only manual placeholders backed by
  `leave_balance_summaries`. They return `calculation_mode: "manual_placeholder"` and
  `external_integration_enabled: false`; no accrual engine, holiday calendar calculation,
  payroll/bordro, SGK, bank, PDKS, AI, or external integration exists. W3C2 regression tests
  explicitly keep this as a stored-summary placeholder.
- OpenAPI uses readable tags: `System`, `Public`, `Dashboard`, `Employees`, `Leave Balances`, and
  `Leave Requests`. Current operations have explicit W3C5 summaries, descriptions, response
  descriptions, and tenant-aware parameter/header descriptions.
- Tenant dependency errors, route-level domain errors, and automatic request validation errors on
  employee, leave balance, and leave request endpoints use the project error envelope.
- FastAPI's generic request validation remains framework default outside the employee and leave
  endpoint scope.
- Local demo seed remains a script command, not an API surface:
  `uv run python scripts/seed_demo_data.py`. It assumes the target local/dev schema already
  exists, then idempotently creates or resets demo tenants, users, employees, and leave requests.
  The command refuses non-local database URL hosts before opening a connection.

## Smoke Coverage

`uv run python scripts/backend_api_smoke.py` runs entirely local/in-memory through ASGI and SQLite.
It does not use deploy, staging URLs, cron, tokens, credentials, `.env`, or external services.

The script currently verifies:

- `/health`, `/`, and `/openapi.json`.
- OpenAPI operation drift: every documented operation must exist in generated OpenAPI, and every
  generated OpenAPI operation must be listed in the documented smoke registry.
- Tenant header missing, invalid, repeated, and cross-tenant behavior.
- Employee create/list/detail/update/delete, filters, pagination, lifecycle status handling, and
  tenant isolation.
- Leave balance read-only summaries, `period_year` filtering, placeholder flags, and tenant
  isolation.
- Leave request create/list/approve/reject/cancel, filters, pagination, transition conflicts,
  cross-tenant user/request checks, date-window behavior, and tenant isolation.
- Dashboard counts, department distribution, recent activity shape, and tenant isolation.

## Verification

W3C5 local gate run:

- `uv run pytest backend/tests/test_openapi_metadata.py`: passed, 8 tests passed, 1 existing
  Starlette `TestClient` deprecation warning.
- `uv run ruff check backend`: passed.
- `uv run pytest`: passed, 292 tests passed, 1 existing Starlette `TestClient` deprecation
  warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, 15 documented
  endpoints covered.

## Remaining Backend Backlog

- Auth/session/RBAC dependencies and permission enforcement.
- Tenant current/settings/onboarding endpoints and user/role management endpoints.
- Standard `{ data, meta }` response envelope, global correlation middleware, and broader
  validation/error normalization beyond employee and leave request endpoints.
- Cursor pagination standardization, sorting controls, and idempotency for critical POST flows.
- Optional leave request detail endpoint if the product workflow needs it.
- Leave policy/accrual calculation, holiday calendars, adjustments/imports, and employee
  self-service leave balance views.
- Documents, reports, and export endpoints in later MVP phases.
- CI/OpenAPI contract governance once workflow-token constraints are resolved outside this task.
