# API Implementation Status Report

Date: 2026-07-10
Branch: `codex/continuous-24h-backend`
Task: `W4A4 Leave request pagination`

## Scope

- Locked the leave request list `limit`/`offset` pagination contract with explicit API, schema,
  service, and OpenAPI regression coverage for the shared default and maximum bounds.
- Kept the completed API surface explicit: 14 generated OpenAPI operations plus the runtime
  `/openapi.json` schema endpoint.
- Clarified leave request pagination bounds in README and API docs without changing the response
  shape.
- No production/staging deploy, cron, token, auth, credential, `.env`, UI, payroll/bordro, SGK,
  banks, PDKS, AI, or external integration changes.
- No request/response payload shape, model, migration, permission, or tenant isolation change.

## Completed API Surface

| Method | Path | Status | Smoke coverage |
|---|---|---|---|
| GET | `/health` | Implemented | Health response, OpenAPI operation, and docs-table registry |
| GET | `/` | Implemented | Wealthy Falcon HR landing response, OpenAPI operation, and docs-table registry |
| GET | `/openapi.json` | Implemented by FastAPI | Generated schema fetch and docs-table registry |
| GET | `/api/v1/dashboard/summary` | Implemented | Tenant-scoped dashboard metrics, OpenAPI operation, and docs-table registry |
| GET | `/api/v1/employees` | Implemented | Tenant list, filters, pagination, OpenAPI operation, and docs-table registry |
| POST | `/api/v1/employees` | Implemented | Tenant create, duplicate protection, OpenAPI operation, and docs-table registry |
| GET | `/api/v1/employees/{employee_id}` | Implemented | Detail lookup, tenant isolation, OpenAPI operation, and docs-table registry |
| PATCH | `/api/v1/employees/{employee_id}` | Implemented | Partial update, lifecycle rules, OpenAPI operation, and docs-table registry |
| DELETE | `/api/v1/employees/{employee_id}` | Implemented | Delete, not-found behavior, OpenAPI operation, and docs-table registry |
| GET | `/api/v1/employees/{employee_id}/leave-balances` | Implemented | Manual summaries, period filter, tenant isolation, OpenAPI operation, and docs-table registry |
| GET | `/api/v1/leave-requests` | Implemented | Tenant list, filters, pagination, OpenAPI operation, and docs-table registry |
| POST | `/api/v1/leave-requests` | Implemented | Pending create, tenant checks, OpenAPI operation, and docs-table registry |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | Implemented | Pending-only transition, tenant checks, OpenAPI operation, and docs-table registry |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | Implemented | Pending-only transition, tenant checks, OpenAPI operation, and docs-table registry |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | Implemented | Pending-only transition, tenant checks, OpenAPI operation, and docs-table registry |

## Current Behavior Notes

- Domain endpoints require exactly one canonical hyphenated UUID `X-Tenant-Id`; `X-Tenant-Slug`
  remains optional but cannot be blank or repeated when sent.
- Employee list supports `department`, `status`, `q`, `limit`, and `offset`. Filters are scoped to
  the current tenant before pagination. `limit` defaults to `50`, is capped at `200`, and `offset`
  defaults to `0`.
- Employee lifecycle validation is active: `terminated` requires `employment_end_date`; `active`
  and `on_leave` require `employment_end_date: null`. Violations return
  `employee_invalid_lifecycle`, and the database also has
  `ck_employees_lifecycle_status_dates`.
- Leave request list supports `status`, `employee_id`, inclusive overlapping `start_date` and
  `end_date` filters, plus bounded `limit` and `offset` pagination. Filters remain scoped to the
  current tenant before pagination. `limit` defaults to `50`, is capped at `200`, and `offset`
  defaults to `0`. Ordering is deterministic by `created_at desc`, `start_date asc`, and `id asc`.
- Leave request decision endpoints currently approve, reject, or cancel only pending requests and
  require the deciding user to belong to the same tenant.
- Dashboard summary is DB-backed and tenant-scoped. It returns active employee count, workforce
  count, pending leave count, new starters this month, department distribution, recent activity,
  and compatibility fields currently used by the frontend-facing contract.
- Leave balance summaries are read-only manual placeholders backed by
  `leave_balance_summaries`. They return `calculation_mode: "manual_placeholder"` and
  `external_integration_enabled: false`; no accrual engine, holiday calendar calculation,
  payroll/bordro, SGK, bank, PDKS, AI, or external integration exists.
- OpenAPI uses readable tags: `System`, `Public`, `Dashboard`, `Employees`, `Leave Balances`, and
  `Leave Requests`. Current operations have explicit summaries, descriptions, response
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

The script now verifies the documented API surface in three directions:

- Every generated OpenAPI operation must be listed in the smoke registry, and every OpenAPI
  operation in the registry must exist in the generated schema.
- The `Completed API Surface` table in this report must match the smoke registry, including the
  runtime `/openapi.json` endpoint.
- The `Güncel uygulama yüzeyi` table in `03-openapi-endpoint-taslagi.md` must match the same smoke
  registry.

The runtime scenarios currently verify:

- `/health`, `/`, and `/openapi.json`.
- Tenant header missing, invalid, repeated, and cross-tenant behavior.
- Employee create/list/detail/update/delete, filters, pagination, lifecycle status handling, and
  tenant isolation.
- Leave balance read-only summaries, `period_year` filtering, placeholder flags, and tenant
  isolation.
- Leave request create/list/approve/reject/cancel, filters, pagination, transition conflicts,
  cross-tenant user/request checks, date-window behavior, and tenant isolation.
- Dashboard counts, department distribution, recent activity shape, and tenant isolation.

## Verification

W4A4 local gate run:

- `uv run ruff check backend`: passed.
- `uv run pytest`: passed, 296 tests passed, 1 existing Starlette `TestClient` deprecation
  warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, 15 documented
  endpoints covered, including documented endpoint table checks.

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
