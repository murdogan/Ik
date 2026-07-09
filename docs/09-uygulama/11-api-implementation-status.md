# API Implementation Status Report

Date: 2026-07-09
Branch: `codex/continuous-24h-backend`
Task: `W1A5 Dashboard enrichment`

## Scope

- Added explicit tenant-scoped dashboard metrics: `active_employee_count` and
  `pending_leave_count`.
- `active_employee_count` counts only employees with `active` status.
- Existing `employee_count` remains the current workforce count (`active` + `on_leave`) and
  `pending_leave_requests` remains as a compatibility field mirroring `pending_leave_count`.
- Dashboard summary continues to return DB-backed `new_starters_this_month`,
  `department_distribution`, and `recent_activity`.
- Dashboard tests now cover active/on-leave separation, pending leave count aliases, unassigned
  department grouping, zero state, tenant header use, and OpenAPI schema exposure.
- Backend API smoke now asserts the enriched dashboard fields.
- Employee list keeps existing `department`, `status`, and `q` filters plus `limit`/`offset` pagination.
- Synced README, backend smoke coverage, and OpenAPI draft status with current API behavior.
- No deploy, staging URL, cron, token, auth, credential, `.env`, UI, or external integration changes.

## Implemented API Surface Covered

- `GET /health`
- `GET /`
- `GET /openapi.json`
- `GET /api/v1/dashboard/summary`, including active employee count, pending leave count,
  this-month starters, department distribution, and recent activity
- Employee CRUD under `/api/v1/employees`, including list filters:
  `department`, `status`, `q`, and `limit`/`offset` pagination
- Leave request list/create/approve/reject/cancel under `/api/v1/leave-requests`, including list
  filters: `status`, `employee_id`, `start_date`, `end_date`, and `limit`/`offset` pagination

## Verification

- `uv run ruff check backend`: passed.
- `uv run ruff check scripts/backend_api_smoke.py`: passed.
- `uv run pytest`: passed, 115 tests passed, 1 existing Starlette `TestClient` deprecation warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`.

## Remaining Backend TODOs

- Auth/session/RBAC dependencies.
- Standard response envelope, correlation metadata, and structured error envelope.
- Sorting/idempotency on list and critical POST endpoints.
- Cursor-based pagination remains a separate future standardization task.
- Additional list filters outside employee and leave request lists remain separate future tasks.
- Optional leave request detail endpoint if product flow needs it.
- Demo seed command remains a separate future task.
