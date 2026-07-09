# API Implementation Status Report

Date: 2026-07-09
Branch: `codex/continuous-24h-backend`
Task: `W1C2 Leave balance placeholder model plan`

## Scope

- Added a minimal `leave_balance_summaries` read model for manually maintained leave balance
  summary placeholders.
- Added `GET /api/v1/employees/{employee_id}/leave-balances` with optional `period_year` filter,
  strict tenant-scoped employee lookup, and `employee_not_found` for cross-tenant employee ids.
- Response fields expose `calculation_mode: "manual_placeholder"` and
  `external_integration_enabled: false`; `remaining_days` is derived from
  `opening_balance_days - used_days - planned_days`.
- Expanded model, schema, API, migration, and smoke coverage for the placeholder behavior.
- No production/staging deploy, cron, token, auth, credential, `.env`, UI, payroll/bordro, SGK,
  banks, PDKS, AI, or external integration changes. The only data-model addition is the
  tenant-scoped `leave_balance_summaries` placeholder table.

## Implemented API Surface Covered

- `GET /health`
- `GET /`
- `GET /openapi.json`
- `GET /api/v1/dashboard/summary`, including active employee count, pending leave count,
  this-month starters, department distribution, and recent activity
- Employee CRUD under `/api/v1/employees`, including list filters:
  `department`, `status`, `q`, and `limit`/`offset` pagination
- Leave balance summaries under `/api/v1/employees/{employee_id}/leave-balances`, including
  `period_year` filter and read-only manual placeholder semantics
- Leave request list/create/approve/reject/cancel under `/api/v1/leave-requests`, including list
  filters: `status`, `employee_id`, `start_date`, `end_date`, and `limit`/`offset` pagination
- Tenant-protected API dependencies require a valid UUID `X-Tenant-Id`; `X-Tenant-Slug` remains
  optional but cannot be blank when sent

## Verification

- `uv run ruff check backend`: passed.
- `uv run pytest`: passed, 173 tests passed, 1 existing Starlette `TestClient` deprecation warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`.

## Remaining Backend TODOs

- Auth/session/RBAC dependencies.
- Full standard response envelope and global correlation middleware.
- Sorting/idempotency on list and critical POST endpoints.
- Cursor-based pagination remains a separate future standardization task.
- Additional list filters outside employee and leave request lists remain separate future tasks.
- Optional leave request detail endpoint if product flow needs it.
- Real leave accrual/policy calculation, holiday calendars, imports, adjustments, and self-service
  `/me` leave balance behavior remain future scope.
