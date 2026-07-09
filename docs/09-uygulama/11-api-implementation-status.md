# API Implementation Status Report

Date: 2026-07-09
Branch: `codex/continuous-24h-backend`
Task: `W2A6 API error consistency`

## Scope

- Standardized automatic request validation `422` responses for employee, leave balance, and
  leave request endpoints onto the project error envelope without changing success response bodies.
- Preserved tenant header error precedence and tenant-scoped service behavior; missing tenant
  headers still return `tenant_header_missing` before route-specific validation mapping.
- Added regression coverage for generic validation failures, employee lifecycle/date-range
  validation, leave balance validation, leave request date-range validation, generated OpenAPI
  error schemas, and `X-Correlation-Id` propagation.
- No production/staging deploy, cron, token, auth, credential, `.env`, UI, payroll/bordro, SGK,
  banks, PDKS, AI, or external integration changes.

## Completed API Surface

| Method | Path | Status | Smoke coverage |
|---|---|---|---|
| GET | `/health` | Implemented | Health response and OpenAPI operation |
| GET | `/` | Implemented | Landing response and OpenAPI operation |
| GET | `/openapi.json` | Implemented by FastAPI | Generated schema fetch |
| GET | `/api/v1/dashboard/summary` | Implemented | Tenant-scoped enriched metrics and OpenAPI operation |
| GET | `/api/v1/employees` | Implemented | Tenant list, filters, pagination, OpenAPI operation |
| POST | `/api/v1/employees` | Implemented | Tenant create and OpenAPI operation |
| GET | `/api/v1/employees/{employee_id}` | Implemented | Detail, tenant isolation, OpenAPI operation |
| PATCH | `/api/v1/employees/{employee_id}` | Implemented | Partial update, lifecycle rules, OpenAPI operation |
| DELETE | `/api/v1/employees/{employee_id}` | Implemented | Delete, not-found check, OpenAPI operation |
| GET | `/api/v1/employees/{employee_id}/leave-balances` | Implemented | Manual summaries, period filter, tenant isolation, OpenAPI operation |
| GET | `/api/v1/leave-requests` | Implemented | Tenant list, filters, pagination, OpenAPI operation |
| POST | `/api/v1/leave-requests` | Implemented | Pending create and OpenAPI operation |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | Implemented | Pending-only transition, tenant checks, OpenAPI operation |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | Implemented | Pending-only transition, OpenAPI operation |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | Implemented | Pending-only transition, OpenAPI operation |

## Current Behavior Notes

- Domain endpoints require a valid UUID `X-Tenant-Id`; `X-Tenant-Slug` remains optional but cannot
  be blank when sent.
- Employee list supports `department`, `status`, `q`, `limit`, and `offset`.
- Employee lifecycle validation is active: `terminated` requires `employment_end_date`; `active`
  and `on_leave` require `employment_end_date: null`. Violations return
  `employee_invalid_lifecycle`.
- Leave request list supports `status`, `employee_id`, inclusive overlapping `start_date` and
  `end_date` filters, plus bounded `limit` and `offset` pagination. Pagination is tenant-scoped
  and uses deterministic ordering by `created_at desc`, `start_date asc`, and `id asc`.
- Dashboard summary is DB-backed and tenant-scoped. It returns active employee count, workforce
  count, pending leave count, new starters this month, department distribution, recent activity,
  and compatibility fields currently used by the frontend-facing contract.
- Leave balance summaries are read-only manual placeholders backed by
  `leave_balance_summaries`. They return `calculation_mode: "manual_placeholder"` and
  `external_integration_enabled: false`; no accrual engine or external integration exists.
- OpenAPI uses readable tags: `System`, `Public`, `Dashboard`, `Employees`, `Leave Balances`, and
  `Leave Requests`. Current operations have explicit summaries and descriptions.
- Tenant dependency, route-level domain errors, and automatic request validation errors on
  employee, leave balance, and leave request endpoints use the project error envelope. Generic
  validation failures on those endpoints return `employee_validation_error`,
  `leave_balance_validation_error`, or `leave_request_validation_error`; date-range and lifecycle
  request validation maps to the existing specific domain codes.
- FastAPI's generic request validation remains framework default outside the employee and leave
  endpoint scope.

## Verification

W2A6 focused preflight:

- `uv run pytest backend/tests/test_employee_api.py backend/tests/test_leave_balance_api.py backend/tests/test_leave_request_api.py backend/tests/test_openapi_metadata.py -q`:
  passed, 66 tests passed, 1 existing Starlette `TestClient` deprecation warning.

Full W2A6 local gate run:

- `uv run ruff check backend`: passed.
- `uv run pytest`: passed, 201 tests passed, 1 existing Starlette `TestClient` deprecation
  warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`.

## Remaining Backend Backlog

- Auth/session/RBAC dependencies and permission enforcement.
- Tenant current/settings endpoints and user/role management endpoints.
- Standard `{ data, meta }` response envelope, global correlation middleware, and broader
  validation/error normalization beyond employee and leave request endpoints.
- Cursor pagination standardization, sorting, and idempotency for critical POST flows.
- Optional leave request detail endpoint if the product workflow needs it.
- Full leave policy/accrual calculation, holiday calendars, adjustments/imports, and employee
  self-service leave balance views.
- Documents, reports, and export endpoints in later MVP phases.
