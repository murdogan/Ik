# API Implementation Status Report

Date: 2026-07-10
Branch: `codex/mvp-phase0-until-20260711-1100`
Task: `P0C Unit of Work transaction boundary and stable error mapping`

## Scope

### P0C transaction and error boundary

- Added `SqlAlchemyUnitOfWork.execute` as the sole begin/commit/rollback owner for the transitional
  `EmployeeCommandHandler` and `LeaveRequestCommandHandler` write paths.
- Employee create/update/delete and leave request create/approve/reject/cancel now run through those
  application command handlers. The underlying business services may `flush()` so constraints and
  generated values are visible, but migrated service methods never `commit()` independently.
- Kept employee/leave/dashboard/balance read paths direct and SQLAlchemy-aware; P0C adds no generic
  repository, distributed transaction abstraction, or god object.
- Added the transport-neutral `ApplicationError` contract and one API-edge mapper. Existing
  employee/leave error status, code, public message, envelope, and correlation behavior remain
  compatible.
- Preserved `409 employee_number_conflict` for both the availability pre-check and the authoritative
  `uq_employees_tenant_employee_number` database constraint. Unknown integrity failures now become
  the safe `409 data_integrity_conflict`; SQLAlchemy `StaleDataError` and recognized database
  concurrency failures become the safe `409 concurrent_write_conflict`, without returning SQL or
  constraint internals.
- Added rollback and fresh-session persistence coverage for flushed employee/leave changes, plus
  command success and typed-error mapping regressions. These tests prove a later command failure
  cannot leave the migrated domain mutation partially persisted.
- P0C changes no table/model schema and adds no Alembic migration. It establishes the boundary that
  later audit/outbox writers can join without implementing those later features now.
- Leave decision winner/locking/versioning and idempotency remain later Phase-0 work. Composite
  tenant foreign keys for tenant-owned relationships likewise remain in the later database-hardening
  migration block; P0C does not claim either issue is fixed.
- No endpoint path, method, success response shape, tenant isolation rule, auth/RBAC behavior, or
  product feature changes. The only new HTTP outcomes are safe stable mappings for persistence
  failures that previously could escape as internal errors.

### Preserved P0A/P0B foundation

- Added the canonical `app.platform` and `app.modules` package skeleton from the master plan,
  without moving employee/leave routes, services, schemas, or SQLAlchemy models.
- Made `app.platform.tenancy.TenantContext` canonical while preserving
  `app.core.tenancy.TenantContext` as the exact same class through a compatibility re-export.
- Extracted the generic API error body/response, exception, and handler to `app.platform.errors`;
  `app.api.errors` keeps every existing public import and module-specific mapping compatible.
- Added an AST-based import-boundary gate with synthetic negative cases and whole-application cycle
  detection. It adds no runtime/dev dependency and causes no lockfile change.
- Documented platform and module ownership, dependency direction, the legacy migration zone, and
  the incremental rollback path in the architecture overview and ADR-002.
- Added an opt-in real PostgreSQL integration lane while preserving the default fast SQLite suite.
- Moved runtime engine/sessionmaker ownership into FastAPI lifespan with deterministic engine
  disposal at shutdown.
- Added environment-driven pool, acquisition/recycle, connect, statement, and idle-transaction
  timeout configuration. PostgreSQL 16 uses `statement_timeout` and
  `idle_in_transaction_session_timeout`.
- Added PostgreSQL Alembic upgrade/downgrade/drift coverage and current-API compatibility coverage
  against an isolated temporary database.
- Preserved the published Alembic revision identifiers and widened PostgreSQL's version column to
  128 characters, including the upgrade path from an existing 32-character column at revision
  0005; SQLite had not enforced this PostgreSQL failure mode.
- Refreshed this implementation status report around the current completed API surface and
  remaining backend backlog.
- Reconfirmed the completed API surface is unchanged: 14 generated OpenAPI operations plus the
  runtime `/openapi.json` schema endpoint.
- Synced README and `03-openapi-endpoint-taslagi.md` notes so the documented surface, current
  behavior, smoke coverage, and backlog language all describe the same backend state.
- Hardened `scripts/backend_api_smoke.py` so it now fails when any endpoint in the documented
  smoke registry is listed in docs but not executed by the smoke runtime scenarios.
- Carried forward W4C5 OpenAPI metadata hygiene: generated docs still use readable tag
  descriptions and tenant-aware operation summaries/descriptions.
- P0A/P0B introduced no endpoint/OpenAPI behavior, response envelope, model, permission, tenant
  isolation, auth/RBAC, or product-feature change.
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
  require the deciding user to belong to the same tenant. P0C moves their commit boundary but does
  not yet add a winner rule, row lock, optimistic version, or idempotency key.
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
- W4C6 is a report and smoke-governance refresh only. It does not add, remove, rename, or change
  any API operation; it confirms the implementation report, OpenAPI endpoint draft, smoke registry,
  and smoke runtime scenarios all agree on the same 15 documented endpoints.
- README and `03-openapi-endpoint-taslagi.md` now carry W4B3 concrete examples for employee
  list/create/detail/update/delete, leave balance summary reads, leave request list/create, and
  approve/reject/cancel decision flows.
- Tenant dependency errors, centrally mapped `ApplicationError` types, and automatic request
  validation errors on employee, leave balance, and leave request endpoints use the project error
  envelope. Route-local domain error translation is no longer the transaction/error boundary.
- W4A6 locks the current public messages for these endpoint families: generic employee validation
  returns `Employee request validation failed`, leave balance validation returns
  `Leave balance request validation failed`, leave request validation returns
  `Leave request validation failed`, duplicate employee numbers return
  `Employee number already exists for this tenant`, and non-pending leave decisions return
  `Only pending leave requests can be decided`.
- P0C adds safe persistence fallbacks: unmapped integrity failures return
  `409 data_integrity_conflict`; stale or recognized concurrent writes return
  `409 concurrent_write_conflict`. The named employee-number unique constraint continues to return
  the more specific existing `409 employee_number_conflict` contract.
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

## P0C Command Transaction Boundary

`EmployeeCommandHandler` and `LeaveRequestCommandHandler` pass one tenant-scoped operation to
`SqlAlchemyUnitOfWork.execute`. The UoW requires an idle request session, opens exactly one
transaction, commits on successful operation completion, and rolls back when the service or a later
composed operation fails. Services flush but do not decide durability. Session lifetime remains
owned by the existing FastAPI database dependency.

Read-only routes continue to call their SQLAlchemy-aware services with the request session directly.
No generic repository has been inserted between query code and SQLAlchemy. No audit/outbox schema is
introduced by P0C, but a future recorder can use the same command session before `execute` commits.
The local demo seed remains a separate script command that already owns one transaction across all
of its tenant/user/employee/leave seed stages; it is not a migrated API leaf service.

Service rollback regressions inspect flushed employee insert/update/delete and leave
create/decision values, roll back, and then use a fresh session to prove that no mutation was
partially persisted. Dedicated forced post-flush command failures cover employee create and leave
decision composition. Successful command regressions likewise use a fresh session to prove that the
outer UoW, rather than the service, committed the write.

## PostgreSQL Baseline and DB Lifecycle

The normal `uv run pytest -q` gate remains the fast SQLite lane. PostgreSQL tests are marked
`postgres` and require an explicit administration URL:

```bash
docker compose up -d --wait postgres
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres uv run pytest -q -m postgres
```

The fixture creates a unique temporary database, runs migration and API scenarios there, and drops
it after the test session; it does not downgrade or clear the database named by the administration
URL. Runtime engine/sessionmaker creation belongs to FastAPI lifespan and shutdown disposes the
engine. Pool and timeout overrides use these environment variables:

- `IK_DATABASE_POOL_SIZE`
- `IK_DATABASE_MAX_OVERFLOW`
- `IK_DATABASE_POOL_TIMEOUT_SECONDS`
- `IK_DATABASE_POOL_RECYCLE_SECONDS`
- `IK_DATABASE_CONNECT_TIMEOUT_SECONDS`
- `IK_DATABASE_STATEMENT_TIMEOUT_MS`
- `IK_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS`

This foundation changes database wiring and test evidence only. The completed API/OpenAPI operation
set and intentional tenant-header compatibility remain unchanged; auth, RBAC, RLS, and new product
features are outside P0A.

## Smoke Coverage

`uv run python scripts/backend_api_smoke.py` runs entirely local/in-memory through ASGI and SQLite.
It does not use deploy, staging URLs, cron, tokens, credentials, `.env`, or external services.

The script now verifies the documented API surface in four directions:

- Every generated OpenAPI operation must be listed in the smoke registry, and every OpenAPI
  operation in the registry must exist in the generated schema.
- The `Completed API Surface` table in this report must match the smoke registry, including the
  runtime `/openapi.json` endpoint.
- The `Güncel uygulama yüzeyi` table in `03-openapi-endpoint-taslagi.md` must match the same smoke
  registry.
- Every endpoint in the smoke registry must be executed by at least one runtime smoke scenario,
  including `/openapi.json` and each tenant-scoped domain path.

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

P0C regression coverage includes:

- service-level no-commit/flush assertions for employee and leave migrated writes;
- forced post-flush rollback with fresh-session persistence checks;
- successful command persistence through the single UoW transaction owner;
- centralized compatibility mapping for existing domain errors, the named employee duplicate
  constraint, unknown integrity conflicts, and stale/recognized concurrent writes;
- existing API, tenant-isolation, OpenAPI operation, migration, and smoke regressions.

Required P0C completion gates are:

- `uv run ruff check backend`
- `uv run pytest -q`
- `uv run python scripts/backend_api_smoke.py`

P0C local gate evidence:

- `uv run ruff check backend`: passed.
- `uv run pytest -q`: passed, 385 fast tests passed and 7 PostgreSQL tests deselected; the one
  existing Starlette `TestClient` deprecation warning remains.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, all 15 documented
  endpoints covered.
- The two new PostgreSQL command-transaction probes cover a synchronized employee unique race and
  real `55P03` lock-conflict mapping. They were collected but could not be executed locally because
  this worktree has neither a running Docker daemon nor an `IK_TEST_DATABASE_URL` admin DSN; the
  configured PostgreSQL lane remains the required runtime evidence for those PostgreSQL-specific
  claims.

Historical P0B local gate evidence retained for continuity:

- `uv run ruff check backend`: passed.
- `uv run pytest -q`: passed, 365 fast tests passed and 5 PostgreSQL tests deselected; the one
  existing Starlette `TestClient` deprecation warning remains.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, 15 documented
  endpoints covered, including documented endpoint table checks, OpenAPI operation drift checks,
  and `documented_endpoint_runtime_coverage`.
- Focused boundary, tenancy, error-contract, employee, leave, OpenAPI, service, and migration
  regressions passed: 203 tests.
- P0B changes no schema, migration, query, transaction, or PostgreSQL-specific behavior, so the
  opt-in PostgreSQL lane was not rerun for a new persistence claim. The P0A PostgreSQL 16.4
  baseline remains 5 integration tests passed.

## Remaining Backend Backlog

- Auth/session/RBAC dependencies, permission enforcement, and current-user context.
- Tenant current/settings/onboarding endpoints plus user/role management endpoints.
- Standard `{ data, meta }` response envelope, global correlation middleware, and validation/error
  normalization beyond the employee and leave endpoint families already covered.
- Cursor pagination standardization, sort controls, response metadata, and idempotency for critical
  POST/decision flows.
- Leave decision winner semantics plus row-lock or optimistic-version enforcement and real
  PostgreSQL concurrency proof.
- Composite `(tenant_id, id)` candidate keys and tenant-consistent foreign keys for current
  employee/user/leave relationships through expand-contract migrations.
- Optional leave request detail endpoint if product workflow needs direct request reads.
- Leave policy/accrual calculation, holiday calendars, manual adjustments/imports, and employee
  self-service leave balance views.
- Employee document, reporting, analytics, and export endpoints in later MVP phases.
- Activating the documented CI template remains repository administration outside this block; the
  template now describes both the fast SQLite and PostgreSQL service-backed test steps.
