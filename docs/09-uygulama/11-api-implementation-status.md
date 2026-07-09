# API Implementation Status Report

Date: 2026-07-09
Branch: `codex/continuous-24h-backend`
Task: `W1A6 API error consistency`

## Scope

- Employee and leave route-level domain errors now return the documented structured envelope:
  `{ "error": { "code": "...", "message": "...", "details": null, "correlation_id": null } }`.
- Covered employee errors: not found, duplicate employee number, and invalid partial-update date
  range.
- Covered leave errors: employee/user/leave request not found, invalid list date range, and
  non-pending transition conflict.
- `X-Correlation-Id` is propagated into the envelope when supplied; otherwise
  `correlation_id` is `null`.
- FastAPI automatic request validation `422` responses remain framework defaults; global response
  envelope/correlation middleware is still a separate future task.
- Employee list keeps existing `department`, `status`, and `q` filters plus
  `limit`/`offset` pagination.
- Dashboard summary keeps DB-backed active/pending metrics, this-month starters, department
  distribution, and recent activity.
- Synced README and OpenAPI draft status with current API behavior.
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
- `uv run pytest`: passed, 116 tests passed, 1 existing Starlette `TestClient` deprecation warning.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`.

## Remaining Backend TODOs

- Auth/session/RBAC dependencies.
- Full standard response envelope and global correlation middleware.
- Sorting/idempotency on list and critical POST endpoints.
- Cursor-based pagination remains a separate future standardization task.
- Additional list filters outside employee and leave request lists remain separate future tasks.
- Optional leave request detail endpoint if product flow needs it.
- Demo seed command remains a separate future task.
