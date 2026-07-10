# API Implementation Status Report

Date: 2026-07-10
Branch: `codex/continuous-24h-backend`
Task: `W4C5 OpenAPI tag hygiene`

## Scope

- Refined OpenAPI tag descriptions for the current `System`, `Public`, `Dashboard`, `Employees`,
  `Leave Balances`, and `Leave Requests` groups.
- Tightened route summaries/descriptions so generated docs show tenant-scoped domain workflows,
  public/system endpoints, and pending leave request decision actions more clearly.
- Updated OpenAPI metadata regression coverage to lock the improved tag catalog and operation
  summary/description text.
- Updated README and OpenAPI endpoint draft notes with the W4C5 metadata-only hygiene scope.
- Kept the completed API surface explicit and unchanged: 14 generated OpenAPI operations plus the
  runtime `/openapi.json` schema endpoint.
- No endpoint behavior, response envelope, model, migration, permission, tenant isolation, or
  service-layer change.
- No production/staging deploy, cron, token, auth, credential, `.env`, UI, payroll/bordro, SGK,
  banks, PDKS, AI, or external integration changes.

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
- W4B4 tightened tenant dependency error text and route regressions: invalid or repeated tenant id
  headers return `tenant_header_invalid` with
  `X-Tenant-Id header must be a single canonical hyphenated UUID`, before unrelated
  payload/query/path validation errors.
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
- W4C2 locks the current limitation: leave balance reads do not derive balances from leave
  requests. A tenant employee with leave request records but no manual balance summary rows gets
  `200 []`.
- OpenAPI uses readable tags: `System`, `Public`, `Dashboard`, `Employees`, `Leave Balances`, and
  `Leave Requests`. W4C5 refines tag descriptions and operation summaries/descriptions for docs
  readability while keeping every path, method, request, response, and tenant requirement
  unchanged.
- README and `03-openapi-endpoint-taslagi.md` now carry W4B3 concrete examples for employee
  list/create/detail/update/delete, leave balance summary reads, leave request list/create, and
  approve/reject/cancel decision flows.
- Tenant dependency errors, route-level domain errors, and automatic request validation errors on
  employee, leave balance, and leave request endpoints use the project error envelope.
- W4A6 locks the current public messages for these endpoint families: generic employee validation
  returns `Employee request validation failed`, leave balance validation returns
  `Leave balance request validation failed`, leave request validation returns
  `Leave request validation failed`, duplicate employee numbers return
  `Employee number already exists for this tenant`, and non-pending leave decisions return
  `Only pending leave requests can be decided`.
- For employee and leave endpoints, tenant header errors are normalized before payload/query/path
  validation errors when both are present; this keeps missing or invalid tenant context from
  exposing unrelated validation details.
- FastAPI's generic request validation remains framework default outside the employee and leave
  endpoint scope.
- Local demo seed remains a script command, not an API surface:
  `uv run python scripts/seed_demo_data.py`. It assumes the target local/dev schema already
  exists, then idempotently creates or resets demo tenants, users, employees, and leave requests.
  The command refuses non-local database URL hosts before opening a connection; local hostnames are
  matched case-insensitively.

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
- Employee create/list/detail/update/delete, filters, pagination, lifecycle status handling, error
  envelopes, and tenant isolation.
- Leave balance read-only summaries, `period_year` filtering, placeholder flags, tenant
  isolation, and the absence of synthetic balances from leave request records.
- Leave request create/list/approve/reject/cancel, filters, pagination, transition conflicts,
  error envelopes, cross-tenant user/request checks, date-window behavior, and tenant isolation.
- Dashboard counts, department distribution, recent activity shape, and tenant isolation.

## Verification

W4C5 local gate run:

- `uv run ruff check backend`: passed.
- `uv run pytest`: passed, 329 tests passed, 1 existing Starlette `TestClient` deprecation
  warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, 15 documented
  endpoints covered, including documented endpoint table checks and OpenAPI operation drift
  checks.

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
