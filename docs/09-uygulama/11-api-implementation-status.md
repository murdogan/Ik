# API Implementation Status Report

Date: 2026-07-14
Branch: `codex/mvp-phase4-employee-master`
Task: `P4B focused Employee 360 profile editing`
Review checkpoint: `P4A preserved; P4B implemented; P4C and later blocks remain unopened`
Review decision: `P4B implementation contract is recorded below for supervisor review`
Push state: `P4B commit is intentionally left unpushed for the supervisor; no merge or deploy`

## Scope

### P4B focused Employee 360 profile editing

- An HR user with `employee:read:tenant` can open the real responsive
  `/employees/{employee_id}` Employee 360 from the P4A directory/create flow. The route exposes
  keyboard-usable **Özet**, **Kişisel**, **İstihdam** and **Organizasyon** tabs with loading,
  empty, error/retry and mobile states. A direct route without employee-read permission is stopped
  by the layout boundary before profile or assignment data clients mount.
- `GET /api/v1/employees/{employee_id}/profile` returns a `{data,meta}` aggregate containing core
  identity/status, focused personal and employment sections with independent positive versions,
  and current assignment plus at most 50 assignment-history rows. Organization data is a read-only
  projection of the existing Phase 3 assignment service/contract; P4B adds no assignment owner or
  write path and does not issue per-tab/per-history-row queries.
- `PATCH .../profile/personal` requires `expected_version`; first/last/work-email compatibility
  changes additionally require `expected_employee_version`. It accepts only first name, last name,
  nullable work email, preferred name, birth date and phone. `PATCH .../profile/employment` follows
  the same section token rule for contract/work type; start-date changes additionally require the
  employee token because that compatibility field remains on `employees`.
- Stale section or core tokens return deterministic `409 concurrent_write_conflict` without a
  partial employee/profile write or audit event. Successful changed rows increment their own token
  once. The command/UoW owns core + section + allowlisted before/after audit atomically; no service
  commit or full payload/employee snapshot is written.
- `0033_p4b_employee_profiles` backfills exactly one `employee_profiles` and one
  `employee_employments` row for every existing employee. Each tenant-owned table has UUID ID,
  tenant and employee IDs, timestamps, positive version, one-row-per-tenant-employee uniqueness and
  a composite employee FK. PostgreSQL uses FORCE RLS, an app-only tenant policy, table
  `SELECT,INSERT`, and column-only UPDATE for approved fields/version/timestamp after inherited ACL
  reset. Changed-data downgrade is refused before either table is dropped.
- P4B adds exactly three operations, bringing the current surface to 77 generated operations and
  78 documented runtime endpoints including `/openapi.json`. Existing P4A employee list/create/
  detail/PATCH/archive contracts remain compatible.
- TCKN/national ID, passport, IBAN/bank, compensation/payroll, health/special-category data,
  address/emergency contacts, documents, leave policy, custom fields, mail, lifecycle/end-date
  actions, assignment writes and all P4C+ modules remain outside P4B.

### P4B verification boundary

Portable migration/model/API/service/transaction/audit/OpenAPI/smoke and frontend gates are part of
the P4B handoff. The opt-in PostgreSQL migration/RLS/ACL/cross-tenant tests are committed, but
`IK_TEST_DATABASE_URL` is unavailable in this execution environment; this report therefore makes
no P4B PostgreSQL runtime-pass claim. The unmodified local ASGI/SQLite executable smoke returned
`BACKEND_SMOKE_OK` with all 78 documented endpoints executed after the two current endpoint tables
were synchronized.

### Historical P4A employee directory and minimal HR create

- An HR director/specialist with `employee:read:tenant` sees **Çalışanlar** in desktop/mobile
  navigation and can open `/employees`; direct routing is permission-gated before employee API
  mounting. Create UI additionally requires `employee:update:tenant`. The authorization catalog is
  unchanged, so `tenant_admin` alone receives neither permission.
- The responsive directory preserves the legacy plain-list API and `X-Next-Cursor`, uses a
  bounded 25-row UI page, and supports name/employee-number/work-email query, status, and current
  legal entity/branch/department/position filters. Catalog failures degrade independently without
  taking down basic search. Loading, error/retry, base-empty and filtered-empty states are explicit.
- The minimal create dialog accepts employee number, first/last name, optional work email, active
  or on-leave status, and start date. It does not chain a structured assignment transaction. On
  success the route-backed `/employees/{employee_id}` summary opens with legacy work labels,
  optimistic version, and the current Phase 3 assignment reference when one exists.
- `0032_p4a_employee_directory` adds generated normalized employee-number/email/full-name columns,
  tenant unique indexes, positive SQLAlchemy optimistic versioning, immutable
  `(tenant_id, id)` and `(tenant_id, status, id)` bounded directory indexes, and missing assignment
  filter indexes without removing legacy columns/history. Non-null
  work email and employee number are trim/lowercase unique per tenant; multiple null emails are
  allowed and blank identifiers are rejected at schema and DB boundaries.
- Create, actual update and first archive write same-transaction `employee.created|updated|archived`
  audit events with allowlisted field names only. Idempotent create replay writes one event.
- Document upload, sensitive identity/financial/health fields, payroll/compensation/performance,
  leave workflow, import/export, report, notification, dynamic fields, hard delete and real mail
  remain outside P4A.

### P4A verification gates

The exact local results are recorded at the P4A commit below. `IK_TEST_DATABASE_URL` and a usable
local PostgreSQL/Docker client are unavailable in this execution environment, so no real
PostgreSQL pass is claimed. Focused opt-in PostgreSQL migration, RLS/ACL, normalized-race and
two-session version tests are committed for the disposable `-m postgres` lane and remain a P4H
execution risk until that lane is run.

| Gate | Command | Result |
|---|---|---|
| Focused employee/assignment backend | `uv run pytest -q backend/tests/test_employee_model.py backend/tests/test_employee_schemas.py backend/tests/test_employee_service.py backend/tests/test_employee_api.py backend/tests/test_employee_transactions.py backend/tests/test_employee_assignment_api.py` | Passed: 162 tests in 32.46s |
| Migration fast lane | `uv run pytest -q backend/tests/test_migrations.py` | Passed: 61 tests in 113.09s; linear head, collision/version preflight, upgrade/downgrade/offline SQL and schema drift |
| OpenAPI compatibility/metadata | `uv run pytest -q backend/tests/test_openapi_contract.py backend/tests/test_openapi_metadata.py` | Passed: 30 tests; one known Starlette/httpx deprecation warning |
| Audit/dashboard regression | `uv run pytest -q backend/tests/test_audit_recorder.py backend/tests/test_audit_api.py backend/tests/test_dashboard.py` | Passed: 20 tests in 12.57s; one known Starlette/httpx deprecation warning |
| Authorization catalog/API | `uv run pytest -q backend/tests/test_authorization_api.py` | Passed: 3 tests in 4.58s; employee API also tests read/update permissions independently |
| Backend Ruff | `uv run ruff check backend scripts/backend_api_smoke.py` | Passed: `All checks passed!` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 75 documented endpoints executed, including P4A create/conflict/version/name/structured-filter/summary behavior |
| Alembic head | `uv run alembic heads` | Passed: sole head `0032_p4a_employee_directory` |
| PostgreSQL P4A path | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p4a_employee_master.py backend/tests/integration/test_postgresql_command_transactions.py` | Not run: disposable PostgreSQL admin DSN/runtime unavailable; test path committed for P4H |
| Frontend lint/typecheck/build | `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, Playwright webServer production build | Passed: exit 0 for lint/typecheck/build |
| Focused browser journey | `cd frontend && PLAYWRIGHT_BROWSERS_PATH=/tmp/pw1223 npm run test:e2e -- --project=chromium tests/employee-directory-flow.spec.ts` | Passed: 2 Chromium tests in 28.9s covering HR create/open and permission-shaped navigation/direct denial |

At that historical checkpoint P4A stopped after the single local commit and P4B had not begun. The
current P4B state is recorded above; the supervisor still owns review and push.

### P3K combined identity and organization hardening gate

- Tenant sign-in accepts only email/password. Credentials are verified before any active
  organization names are returned; a one-membership identity enters directly while a multi-org
  identity receives a short-lived, one-use organization-selection transaction. Selection replay,
  key tampering, membership changes, cross-identity use and cross-tenant substitution fail closed.
- Platform sign-in has its own route, refresh cookie, audience, server-side session and tenantless
  principal. Platform credentials cannot authorize tenant APIs and tenant credentials cannot
  authorize platform APIs. Switching organizations revokes the source tenant session family.
- The historical dashboard, employee, leave-balance and leave-request APIs now derive tenant scope
  only from a validated live tenant session. Caller tenant headers are ignored and cannot select
  scope; exact read/update/manage permissions protect all twelve migrated operations.
- The P3F-P3J organization product remains manually usable through one role-aware workspace:
  legal entities, branches, cycle-safe departments, positions, effective-dated assignments,
  manager-derived team scope and a bounded lazy org chart. Archived references remain readable but
  cannot receive new assignments.
- Migration `0031_p3k_legacy_tenant_auth_boundary` adds the exact
  `leave:manage:tenant` catalog permission for HR director/specialist and is the sole Alembic head.
  The populated PostgreSQL gate independently exercises the `0030` legacy-string backfill before
  upgrading to head; no Phase 4 employee-master expansion is included.
- The demo seed gives one canonical identity two active tenant memberships and a separate active
  platform super-admin role. `--auth-demo` also emits labeled, short-lived activation URLs for the
  tenant admin and manager demo identities without persisting or printing a password.

### P3K verification gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend scripts/backend_api_smoke.py scripts/seed_demo_data.py` | Passed: `All checks passed!` |
| Full fast backend suite | `uv run pytest -q` | Passed: 855 tests; 57 PostgreSQL tests deselected; one known Starlette/httpx deprecation warning |
| Migration fast lane | `uv run pytest -q backend/tests/test_migrations.py` | Passed: 56 tests; one linear head, SQLite/offline compatibility, catalog parity and expand-contract round trips |
| Alembic head | `uv run alembic heads` | Passed: sole head `0031_p3k_legacy_tenant_auth_boundary` |
| OpenAPI contract | `uv run pytest -q backend/tests/test_openapi_contract.py backend/tests/test_openapi_metadata.py` | Passed: 29 tests; 74 generated operations, exact tenant/platform bearer split and 401/403 metadata on the twelve migrated operations |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 75 documented endpoints executed, including realm cross-use, tenant-header spoof resistance and employee leave-mutation denial |
| Full PostgreSQL lane | `IK_TEST_DATABASE_URL=postgresql+asyncpg://hermes@127.0.0.1:55433/postgres uv run pytest -q -m postgres` | Passed: 57 tests; real migrations, RLS/grants, realm and membership attacks, department concurrency, organization history, manager scope and migrated API smoke |
| Populated backfill and bounded team query | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p3k_assignment_gate.py` | Passed: 2 tests; deterministic populated `0029 -> head` backfill and 2,481-row team fixture with 3 SELECTs/5 statements per 25-row page plus manager index `EXPLAIN ANALYZE` evidence |
| Frontend static gates | `npm --prefix frontend run lint`, `typecheck`, `build` | Passed; lint/typecheck/build exit 0 and the production build generated 15 static pages |
| Browser E2E | `npm --prefix frontend run test:e2e` | Passed: 26 Chromium flows covering email-only multi-org login, platform realm, administration, assignments, manager team, lazy chart and denial states |
| Git hygiene | `git diff --check` plus final scope review | Passed; no Phase 4, deployment, environment, secret, credential or generated-artifact change |

The queue stops after the local P3K commit. Codex does not push, merge or deploy; the supervisor
owns the review-branch push, then Murat review is required before Phase 4.

### P3J lazy organization chart and unified workspace

- Tenant admin and HR users open one role-aware Organization workspace for legal entities,
  branches, departments, positions, employee assignments and a reporting chart. Ordinary
  employees neither see its navigation nor mount its APIs.
- `GET /api/v1/org-chart` returns only roots or one requested manager's direct reports. Every
  level is capped at 100, cursor-bound to its parent and contains resolved work-organization
  labels plus `has_children`; descendants are never downloaded until expanded.
- The read path uses fixed-count joined queries with correlated child existence checks. A
  tenant-scoped normalized work-email compatibility link supports employee managers until the
  explicit Employee/User relation planned for Phase 4; referenced manager-only Users remain
  visible as synthetic roots.
- Current assignments retain readable archived entity/branch/department/position labels, while
  terminated or archived employees and ineffective assignment intervals are excluded.
- P3J does not infer whole-tenant reporting cycles through the transitional email link. A closed,
  disconnected cycle in pre-existing assignment data can therefore have no root; explicit
  Employee/User linkage and reporting-graph integrity remain deferred to the planned later work
  instead of adding an unbounded recursive read or changing P3I assignment semantics here.

### P3J verification gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend scripts/backend_api_smoke.py` | Passed: `All checks passed!` |
| Full fast backend suite | `uv run pytest -q` | Passed: 855 tests; 55 PostgreSQL tests deselected; one known Starlette/httpx warning |
| Focused org-chart/OpenAPI regression | `uv run pytest -q backend/tests/test_org_chart_api.py backend/tests/test_openapi_contract.py` | Passed: 11 tests covering tenant/RBAC/feature denial, mixed root and parent cursor walks, archive retention, Unicode-safe cursors and fixed 3/4-statement representative reads |
| Alembic head | `uv run alembic heads` | Passed: sole unchanged head `0030_p3i_employee_assignments`; P3J adds no persistence migration |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 75 documented endpoints executed, including lazy root and direct-report chart reads |
| Frontend static gates | `npm run lint`, `npm run typecheck`, `npm run build` in `frontend/` | Passed; production build includes the unified `/organization` workspace and dashboard entry |
| Organization browser regression | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npm run test:e2e --` with the five organization specs | Passed: 9 Chromium flows covering dashboard entry, lazy-only expansion, retry, empty/archive/pagination states, unauthorized and disabled-feature denial, and existing entity/branch/department/position/assignment behavior |
| Git hygiene | `git diff --check` plus independent backend/frontend/test scope review | Passed; no Phase 4, migration, deployment, environment, credential or generated-artifact change |

### Historical P3I employee assignments and derived manager team scope

- Authorized tenant admin/HR users can assign an employee to a legal entity, branch, department,
  position and optional manager from the existing `/organization` workspace, then schedule a
  dated change while retaining the prior assignment as readable history.
- Every new assignment validates active organization references. Assignment changes close and
  supersede the prior row in the same transaction, update the legacy employee projection, and
  record assignment and reporting-line audit events atomically.
- Legacy employee reads, filters and dashboard department distributions prefer the current
  structured assignment and fall back to the retained free-text fields only when no current
  assignment exists. The expand-contract migration backfills legacy employees without removing
  those fields.
- `/teams/me` derives direct reports exclusively from the authenticated manager's effective
  assignments. It uses bounded, opaque-cursor pagination and does not accept an employee or
  manager selector, so a manager cannot broaden the derived scope through request parameters.
- PostgreSQL FORCE RLS, narrow runtime ACLs and assignment-history triggers are proven on an
  isolated local PostgreSQL 17.10 database, including tenant isolation, archived-reference
  rejection, the owner-only terminated-history import exception and immutable history.

### P3I verification gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend scripts/backend_api_smoke.py` | Passed: `All checks passed!` |
| Focused backend regression | `PYTHONPATH=backend uv run pytest -q` with the assignment, employee, dashboard, demo seed, migration, OpenAPI, audit and dependency suites | Passed: 213 tests; one known Starlette/httpx warning |
| Alembic head | `uv run alembic heads` | Passed: sole head `0030_p3i_employee_assignments` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 74 documented endpoints executed, including assignment create/read/change/history and derived team scope |
| PostgreSQL P3I proof | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p3i_employee_assignments.py` | Passed: one focused test on isolated PostgreSQL 17.10 covering FORCE RLS, ACLs, tenant isolation, archived-reference rejection and immutable effective history |
| Frontend static gates | `npm run lint`, `npm run typecheck`, `npm run build` in `frontend/` | Passed; production build includes `/organization` and manager team dashboard UI |
| Browser E2E regression | `npm run test:e2e` with the installed Chromium executable | Passed: 24 flows, including two P3I flows covering server-side employee search, create/change/history pagination, non-team exclusion and derived-team pagination |
| Git hygiene | `git diff --check` plus independent backend/frontend/scope review | Passed; no Phase 4, deployment, environment, credential or generated-artifact change |

### Historical P3H position catalog

- Authorized tenant admin/HR users can create reusable job titles with stable codes, search and
  paginate the tenant catalog, rename active titles, archive them and retain readable history from
  the existing `/organization` workspace. Budget, FTE, occupancy, manager and workforce-planning
  fields remain out of scope.
- Stable codes are tenant-unique and remain reserved after archive. Archived positions are
  terminal, expose `accepts_new_assignments=false`, reject updates and are rejected by the
  assignable-position service boundary prepared for the later structured-assignment slice.
- Every API and service read/write derives tenant and actor only from the authenticated request
  context, reuses organization read/update RBAC and rollout/lifecycle guards, and records
  create/update/archive audit events in the domain transaction.
- Status/search-bound opaque cursors cap pages at 100. One- or two-character searches are exact
  stable-code B-tree lookups; longer contains searches accept at most 100 characters, require an
  indexable three-character word trigram and use PostgreSQL code/title GIN indexes.
- The additive `positions` table preserves the legacy `employees.position` string. PostgreSQL
  FORCE RLS, narrow column ACLs and an immutable/terminal-history trigger are covered by a focused
  test that passed on an ephemeral local PostgreSQL 17.10 database.

### Historical P3H verification gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend scripts/backend_api_smoke.py` | Passed: `All checks passed!` |
| Full fast backend suite | `uv run pytest -q` | Passed: 842 tests; 54 PostgreSQL tests deselected; one known Starlette/httpx warning |
| Focused migration/API | `uv run pytest -q backend/tests/test_migrations.py backend/tests/test_position_api.py` | Passed: 57 tests |
| Alembic head | `uv run alembic heads` | Passed: sole head `0029_p3h_position_catalog` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 68 documented endpoints executed, including position search/update/archive/history |
| PostgreSQL P3H proof | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p3h_positions.py` | Passed: one focused test on ephemeral PostgreSQL 17.10 covering RLS/ACLs, indexes, generated normalization, tenant isolation, lifecycle trigger and downgrade retention guard |
| Frontend static gates | `npm run lint`, `npm run typecheck`, `npm run build` in `frontend/` | Passed; production build includes `/organization` |
| Focused browser E2E | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npx playwright test tests/position-catalog-flow.spec.ts tests/organization-flow.spec.ts tests/department-hierarchy-flow.spec.ts` | Passed: five Chromium flows including position create/search/page/update/archive/history and existing organization regressions |
| Git hygiene | `git diff --check` plus independent backend/frontend/scope review | Passed; no Phase 4, planning, deployment, environment, credential or generated-artifact change |

### Historical P3G department hierarchy

- HR can create root/child departments, lazily expand one bounded level, rename active nodes,
  safely move them, archive leaves and read archived parent/code history from `/organization`.
- Stable codes are tenant-unique and reserved after archive. Active children can only use active
  parents; archived nodes are terminal, cannot accept new assignments and retain their final
  parent link for historical reads.
- Application ancestry checks provide immediate conflict responses. PostgreSQL row and statement
  triggers enforce the final graph, while a tenant-scoped version fence prevents stale
  `REPEATABLE READ`/`SERIALIZABLE` writers from committing opposing moves concurrently.
- Department and internal fence tables use tenant FORCE RLS and narrow runtime ACLs. Read/update
  RBAC is enforced at API and service boundaries, and create/update/archive audit writes share the
  domain transaction.
- Flat and tree APIs use filter-bound opaque cursors with a hard page cap of 100; no endpoint
  returns an unbounded recursive tenant tree.

### P3G verification gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend` plus focused script Ruff | Passed: `All checks passed!` |
| Focused backend slice | `uv run pytest -q backend/tests/test_organization_api.py backend/tests/test_openapi_contract.py backend/tests/test_migrations.py` | Passed: 66 tests |
| Alembic head | `uv run alembic heads` | Passed: sole head `0028_p3g_department_hierarchy` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 63 documented endpoints executed, including department lazy tree/move/cycle/archive/history |
| PostgreSQL P3G proof | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p3g_departments.py` | Passed on a disposable PostgreSQL 17 database: RLS/ACL, immutable code/history, multi-row cycle, concurrent `READ COMMITTED`, pre-established `REPEATABLE READ` and `SERIALIZABLE` snapshots |
| Frontend static gates | `npm run lint`, `npm run typecheck`, `npm run build` in `frontend/` | Passed; production build includes `/organization` |
| Focused browser E2E | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npm run test:e2e -- tests/department-hierarchy-flow.spec.ts` in `frontend/` | Passed: one Chromium flow covering lazy expansion, first-child rendering, create, rename, move, archive and history |
| Git hygiene | `git diff --check` plus independent backend/frontend task-scope review | Passed; no deployment, cron, secret or post-P3G module change |

### Historical P3F legal entities and branch/location

- Every existing and newly provisioned tenant has one deterministic active default legal entity.
  Authorized tenant admin/HR users can read and edit legal settings while stable codes and the
  default marker remain immutable.
- Branches carry tenant-unique stable codes, IANA timezones, typed location data and active/archive
  lifecycle state. Archive retains the row and code for history, rejects later mutation and marks
  the branch unavailable for new assignments.
- All nine bearer-authenticated organization operations use current-session tenant scope, exact
  read/update permissions, the authoritative `organization` rollout flag, bounded cursor lists
  and same-transaction redacted audit events. Disabled or missing rollout state fails closed.
- The `/organization` screen exposes legal-entity editing plus branch create, edit, filtering,
  pagination and archive/history workflows to authorized tenant admin/HR roles.

### Historical P3F verification gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend/app backend/tests scripts` | Passed: `All checks passed!` |
| Full fast backend suite | `uv run pytest -q` | Passed: 832 tests; 52 PostgreSQL tests deselected; one known Starlette/httpx deprecation warning |
| Alembic head | `uv run alembic heads` | Passed: sole head `0027_p3f_legal_entities_branches` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 57 documented runtime endpoints executed, including all nine P3F operations |
| PostgreSQL P3F proof | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p3f_organization.py` | Not run locally: `IK_TEST_DATABASE_URL` is unavailable; the test is collected and covers RLS/ACLs, provisioning policy, stable history, cross-tenant denial and lifecycle concurrency |
| Frontend static gates | `npm run lint`, `npm run typecheck`, `npm run build` in `frontend/` | Passed; production build includes `/organization` |
| Focused browser E2E | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npx playwright test tests/organization-flow.spec.ts` in `frontend/` | Passed: 3 Chromium tests covering admin CRUD/archive, permission denial and rollout denial |
| Git hygiene | `git diff --check` plus independent task-scope review | Passed; no deployment, staging, cron, secret or post-P3F module change |

### Historical P3E Phase 3A identity checkpoint closure

- Tenant admins can invite either a new email or an existing global identity. A new identity uses
  the hashed, expiring activation link once to establish its first Argon2id password. An existing
  active identity submits its current password through the same one-use link; the server verifies
  and preserves the global hash while activating only the pending tenant membership.
- Tenant login remains email/password only. Membership names are resolved only after successful
  global credential verification; two active demo memberships produce the existing safe,
  short-lived organization-selection flow.
- Password recovery is available from `/login`. Request returns the same `202 {status: accepted}`
  for known, unknown and inactive emails and never returns a reset URL, identity or organization.
  The delivery port uses a local/dev console fake only; production mail integration remains outside
  this task. Confirm consumes a hashed 15-minute token once, reconciles legacy credential
  projections, and revokes tenant sessions, platform sessions and pending organization selections.
  Invited legacy users deliberately keep a null local hash, so an existing identity can still be
  safely reinvited and activate that pending membership with the new global password after reset.
- Credential verification and session creation are serialized on the global identity row. A reset
  that wins the lock makes an in-flight tenant/platform login fail generically; a login that wins
  creates its family before reset atomically revokes it. Reset issue/completion use the same lock
  order and take terminal timestamps only after waiting, preserving expiry and timestamp checks.
- Revision `0026_p3e_identity_checkpoint` is additive. `password_reset_tokens` is FORCE-RLS,
  tenant/platform/authentication capabilities have no table access, and a narrow non-login
  recovery owner exposes atomic issuance, token-checked completion and exact-hash locking only
  through narrow functions. Credential-lock execution is granted reciprocally to the
  authentication or current-tenant capability; platform and cross-tenant calls are denied.
  Reused-role stale grants are cleared, unexpected owner members or pre-owned public objects fail
  closed, and reset-confirm source/token limits run before Argon2id.
- The current demo seed upgrades the pre-P3 Atlas admin without replacing its stable membership
  ID: that membership is repointed to the shared canonical admin identity, a detached historical
  identity is retained for possible references, conflicting non-null hashes fail closed, and a
  second seed run is idempotent.
- At the time it was committed, this checkpoint closed Phase 3A only and contained no legal
  entity, branch, department, position, assignment or other P3F organization work.

### P3E Phase 3A identity checkpoint gates

| Gate | Command | Result |
|---|---|---|
| Backend Ruff | `uv run ruff check backend scripts` | Passed: `All checks passed!` |
| Full fast backend suite | `uv run pytest -q` | Passed: 825 tests; 51 PostgreSQL tests deselected; one known Starlette/httpx deprecation warning |
| Focused P3E contracts | `uv run pytest -q backend/tests/test_auth_api.py backend/tests/test_demo_seed_command.py backend/tests/test_demo_seed_service.py backend/tests/test_migrations.py backend/tests/test_openapi_contract.py backend/tests/test_openapi_metadata.py` | Passed: 111 tests; one known Starlette/httpx warning |
| Alembic head | `uv run alembic heads` | Passed: sole head `0026_p3e_identity_checkpoint` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 48 documented runtime endpoints executed |
| Full PostgreSQL 17.10 lane | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed: 51 tests; migration round-trip/drift, hostile reused-role cleanup, exact RLS/ACLs, credential/reset serialization, safe pre-P3 demo upgrade, invitation acceptance, reset atomicity and all prior persistence gates |
| Frontend static gates | `npm run lint && npm run typecheck && npm run build` in `frontend/` | Passed; production build includes `/forgot-password` and `/reset-password` |
| Full browser E2E | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npm run test:e2e` in `frontend/` | Passed: 17 Chromium tests, including recovery and existing-identity activation → organization selection |
| Git hygiene | `git diff --check` plus task-scope review | Passed; no deployment, staging, cron, secret, P3F organization or later-phase change |

The committed P3E checkpoint is the explicit Phase 3A completion boundary. Codex does not push,
merge or deploy; the supervisor owns the review-branch push before any P3F work begins.

### Historical P3B email-first tenant login and post-auth membership discovery

- `POST /api/v1/auth/login` accepts exactly normalized email and password. It reads the global
  credential projection and completes constant-work Argon verification before any membership
  query. Unknown identity, wrong password, inactive identity and no eligible membership all use
  the same tenantless `401 invalid_credentials` contract and platform-safe failure audit shape.
- One active membership is rechecked inside the tenant transaction and creates the existing
  tenant-bound access/refresh session. Multiple active memberships create no session or cookie;
  they return only tenant display names, random choice keys and a hash-at-rest selection
  transaction with a five-minute default expiry. Selection consumption is intentionally left to
  the next authorized identity slice.
- The public login path has database-backed HMAC-keyed source and global-identity fixed-window
  buckets. Raw network/email values are not persisted, rotating source addresses cannot reset the
  identity bucket, `429` responses carry `Retry-After`, and credential/rate-limit denials retain
  the allowlisted global login-failure audit event.
- PostgreSQL uses a third, mutually exclusive `wealthy_falcon_authentication` capability. Its
  pre-existing object/column grants are reset before exact column grants are applied; it cannot
  read HR data, private identity/membership display fields, selection rows or platform data beyond
  the login projection. Its audit `INSERT` policy accepts only the exact redacted login-failure
  shape. Tenant and platform capabilities cannot read selection credentials.
- Historical P3B invitation and activation remained expand-compatible for absent/pending identities and projected the
  legacy user/membership/roles in the same transaction. A tenant invitation cannot reset an
  already-active global identity: that activation is rejected without consuming its token or
  changing either credential. If a pending identity changes state concurrently, the projection
  function rejects and rolls back the whole activation transaction. Existing-identity membership
  acceptance required a later identity-authenticated flow. P3E above now supplies that verified
  current-password acceptance without replacing the global credential.
- `/login` now asks only for email and password. A single-organization user reaches the dashboard
  automatically; a verified multi-organization user sees safe organization names while the raw
  selection transaction remains only in expiring component memory and is never rendered or stored
  in browser storage.

At the historical P3B checkpoint, the Phase-2 local/manual invitation response still contained its raw activation URL. An authorized
tenant inviter can therefore distinguish a new/pending global account (activatable) from an
already-active/locked/disabled account (generic rejection), although no organization membership
metadata was returned. P3E closes the visible behavior with the same response shape: both new and
existing identities receive a usable link, while only the existing credential owner can activate
the pending membership.

### Historical P3B local gate evidence

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed, `All checks passed!` |
| Fast SQLite | `uv run pytest -q` | Passed, 809 tests; 46 PostgreSQL tests deselected; one known Starlette warning |
| Focused auth/migration/OpenAPI | `uv run pytest -q backend/tests/test_auth_api.py backend/tests/test_migrations.py backend/tests/test_openapi_metadata.py backend/tests/test_database_tenant_access.py` | Passed, 91 tests; one known Starlette warning |
| PostgreSQL 17.10 | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_baseline.py backend/tests/integration/test_postgresql_p3a_identity_memberships.py backend/tests/integration/test_postgresql_p3b_email_first_login.py backend/tests/integration/test_postgresql_f2e_audit.py backend/tests/integration/test_postgresql_f2f_query_smoke.py` | Passed, 17 focused migration/RLS/auth/audit/query tests; two known computed-default warnings |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed, `BACKEND_SMOKE_OK`; 40 documented endpoints |
| Frontend | `npm run lint`, `npm run typecheck`, `npm run build` | Passed with Next.js 16.2.10 |
| Focused browser | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=... npm run test:e2e -- session-flow.spec.ts role-aware-navigation.spec.ts` | Passed, 5 Chromium tests |

### Historical F2F Phase 2 product hardening, manual-demo gate and focused regression

- At the F2F checkpoint, this hardened the completed F2A–F2E product without adding a new route,
  screen, table/column, domain
  module or Phase 3 organization behavior. The reviewable product flow is invitation → fragment
  activation → tenant-aware login → protected workspace → refresh rotation → logout, followed by
  tenant-admin user/role administration and redacted audit exploration.
- At that checkpoint, the live contract had 39 generated operations: all 24 historical F1E
  operations remained exact and
  15 F2 auth/user/RBAC/audit operations are additive. Runtime `/openapi.json` makes the synchronized
  docs/smoke registry 40 rows. F2F uses an explicit additive-set assertion plus executable OpenAPI
  metadata and smoke coverage; it does not create another full per-block snapshot.
- One consolidated role × scope × endpoint matrix covers every seeded tenant role without
  repeating the removed lower-level denial cases: tenant admin has the full user/role/audit
  surface; IT admin has user-read plus security-audit access; HR director and auditor receive their
  explicit audit categories; HR specialist, manager and employee are denied the general admin/audit
  center. Hidden/cross-tenant resources fail as indistinguishable `404`s and platform audit remains
  a separate trusted boundary.
- F2 database behavior remains PostgreSQL-specific where required. Migrations add hashed
  activation/session credentials, system RBAC, tenant-bound assignments and append-only audit
  storage; FORCE RLS, least-privilege runtime grants, transaction-local tenant binding, audit redaction and
  write-plus-audit rollback are proved only by the dedicated `-m postgres` lane, never by SQLite.
- F2F adds one PostgreSQL-only forward grant revision, `0021_f2f_user_insert_grant`. It repairs the
  minimum runtime `INSERT(permission_version)` capability required by ORM-created invited users;
  the server/database still owns the positive default, no caller field is exposed, and the runtime
  role receives neither table-wide INSERT nor INSERT on legacy `can_invite_users`.
- The bounded-query smoke measures query counts rather than unstable wall-clock thresholds for
  login, user list and audit list. Lists retain capped cursor pagination and a `limit + 1` probe;
  the smoke is intended to catch obvious N+1/query-budget regressions, not claim production load
  capacity.

### Historical F2F reviewable browser surface

| Route | Visible outcome | Access boundary |
|---|---|---|
| `/activate#token=…` | One-time invitation activation and password setup; fragment is removed before API submission | Invitation credential only |
| `/login` | Email-first global credential verification; one membership auto-selects and multi-membership output is display-safe | Public credential exchange followed by post-auth membership discovery |
| `/dashboard` | Protected tenant shell and session restore/refresh | Authenticated tenant user |
| `/users` | Search/page/detail, invite, status/name update and exact role replacement | Tenant admin permissions; employee redirects before admin API mount |
| `/audit` | Read-only filtered/paged redacted tenant security and administration history | `audit:read:tenant`; employee redirects before audit API mount |
| `/platform` | Separate platform workspace without tenant navigation or customer HR context | Platform workspace identity; not seeded by the local tenant-admin demo |
| `/platform/audit` | Platform-operations-only audit explorer UI and browser separation gate | Backend remains a trusted `PlatformPrincipal` boundary; bearer alone cannot unlock it and no tenant audit API is called |

### Historical F1E local Phase 1 security, product and contract closure

- Completes the local Phase 1 technical gate without adding a route, response field, database
  revision, authentication/RBAC implementation or persistent audit store. Final closure remains
  pending the supervisor-owned push and Murat review. At that checkpoint, the surface remained 24 generated
  OpenAPI operations and a 25-row documented/smoke registry including runtime `/openapi.json`.
- All ten Phase 1 platform/tenant operations now carry exact
  `x-required-principal=platform|tenant` OpenAPI metadata matching their executable injected
  principal dependency. They retain documented `403` fail-closed responses. Phase 1 deliberately
  advertises no bearer/API-key scheme or standard OpenAPI `security` entry because caller-facing
  authentication begins only in Phase 2.
- One authorization matrix proves every Phase 1 operation denies absent or spoofed caller context;
  authorized dependency overrides execute the same operations in API tests and the 25-endpoint
  smoke. Tenant A/B API, service and cache-helper isolation remains covered. Every worker job has a
  non-zero tenant and explicit `REQUEST|SYSTEM` origin. Request jobs require matching context, so
  A→B and B→A envelopes are rejected before the recording fake can enqueue; system jobs explicitly
  reject request context. The PostgreSQL lane proves catalog, repository, raw-SQL, relationship and
  platform-to-HR negatives.
- Platform response and OpenAPI assertions exclude document, employee, user and leave payload
  schemas/fields. `limits.active_employees` remains nullable configured tenant metadata and is not
  an employee record, usage value or count.
- Unsafe caller correlation values are regenerated and excluded from response/error, structured-log
  and recorded-event fixtures. Events retain only validated request/trace identifiers and the
  closed redacted Phase 1 contracts; no audit persistence claim is introduced.
- The complete PostgreSQL 17.10 lane, focused Alembic upgrade/downgrade/drift baseline, RLS/direct-DB
  attacks, fast suite, OpenAPI contract, smoke and sole-head checks passed with the exact commands
  recorded below. The queue stops here for Murat review and must not begin Phase 2 automatically.

### Historical F1D typed rollout, platform metadata hardening and event contracts

- Adds three visible operations:
  `GET/PATCH /api/v1/platform/tenants/{tenant_id}/features` and
  `GET /api/v1/tenant/features`. Current target is 24 generated OpenAPI operations and runtime
  `/openapi.json` for a 25-row documented/smoke registry. Historical Phase-0/F1A/F1B snapshots stay
  immutable; F1D owns an explicit additive/component diff.
- The code-owned ordered flag catalog is `organization`, `employees`, `documents`, `leave`,
  `self_service`, `reporting`, `notifications`. Only `employees`, `leave`, `reporting` default true.
  Effective reads always return all seven in that order with `source=default|override`; unknown,
  duplicate or non-boolean writes fail closed and customer-specific forks are not supported.
- Migration `0015_f1d_feature_flags` adds `tenant_feature_flags(tenant_id,key)` with fixed checks,
  tenant-root FK, existing-tenant default backfill and downgrade refusal when overrides exist. It
  also adds nullable checked `tenants.active_employee_limit`, serialized only as configured
  `limits.active_employees` metadata—not as an HR usage counter.
- PostgreSQL feature state is FORCE-RLS protected. Tenant capability receives tenant-scoped SELECT;
  platform capability receives SELECT/INSERT/UPDATE; neither receives DELETE. The PostgreSQL 17.10
  lane passed catalog/raw A-B/platform-HR, hostile-default-ACL and non-BYPASS migration-owner tests;
  SQLite is not used as proof for these grants/policies.
- Platform list/detail now use a dedicated query service that explicitly projects allowlisted
  `tenants` columns only. It does not import/join/count employee, user, leave or document models.
  Responses expose identity, plan/region/locale/timezone, lifecycle-derived health, configured
  limit and timestamps only.
- Lifecycle hardening rejects combining an `offboarding` or `closed` transition with metadata/limit
  mutation, and requires data-region changes to finish while status remains `provisioning`. Closed
  remains terminal, offboarding remains closure-only, and same-value/status/flag updates do not emit
  change events.
- Exactly four frozen/extra-forbid CORE application contracts exist: `tenant.created`,
  `tenant.status_changed`, `tenant.setting_changed`, `feature_flag.changed`. They carry fixed
  tenant/platform-ops audit metadata and only typed deltas; generic payload/metadata/entity
  snapshots, passwords/hashes/tokens/OTP/secrets and employee/HR/sensitive fields are structurally
  rejected. Both recorder adapters additionally require one of the four exact registered classes;
  the marker, structural lookalikes, and sensitive-field subclasses are rejected.
- Tenant commands invoke an async `PlatformEventRecorder` inside the command UoW callback. Phase 1
  defaults to a discarding adapter and therefore makes no persistence claim; Phase 2 can replace
  the same port with same-session append-only persistence. F1D adds no `audit_events` table, audit
  read route, retention/index or full audit center.
- Platform and tenant dependencies remain fail closed and Phase-2 replaceable. A tenant principal
  cannot call platform list/detail/status/feature routes, and caller header/path/body/query identity
  cannot construct platform authority or change current tenant scope.

### Historical F1C PostgreSQL RLS foundation and transaction tenant binding

- Migration `0014_f1c_postgresql_rls` enables and forces RLS on every current tenant-owned table:
  `users`, `employees`, `leave_requests`, `leave_balance_summaries`, `command_idempotency` and
  `tenant_settings`. It also scopes the `tenants` metadata root by `id` for the normal app role.
  The migration inventory is frozen; an independent catalog test discovers every public non-null
  `tenant_id` table and fails on inventory, policy or FORCE drift.
- Normal database capability role `wealthy_falcon_app` and separate metadata-only capability role
  `wealthy_falcon_platform` are `NOLOGIN`, `NOINHERIT`, `NOSUPERUSER` and `NOBYPASSRLS`. The app
  role receives only current product tenant-table privileges; tenant-root updates are column-bound
  to locale/timezone plus ORM timestamp. Platform receives tenant metadata DML and provisioning-only
  settings INSERT, but no settings SELECT/UPDATE or HR-table privilege. Actual forbidden raw SQL
  fails with PostgreSQL `42501`.
- App policies use both `USING` and `WITH CHECK` against
  `nullif(current_setting('app.tenant_id', true), '')::uuid`. Missing/empty context exposes zero
  rows, malformed UUID context aborts, and cross-tenant raw INSERT/UPDATE is rejected. Tenant root
  metadata is subject to the same scope.
- HTTP request dependencies select one immutable database path per session. Tenant transactions
  execute `SET LOCAL ROLE wealthy_falcon_app` and `SET LOCAL app.tenant_id`; platform transactions
  execute only their separate local role. Command UoW materializes that binding before the
  operation, while read-only SQLAlchemy autobegin transactions use the same `after_begin` seam.
- Both role and tenant setting are transaction-local. A pool-size-one PostgreSQL test proves the
  same backend PID resets after commit and rollback, does not expose a missing-context tenant, and
  rebinds A/B plus repeated UoW transactions safely.
- Real PostgreSQL tests prove app-role raw SQL and repository negatives, platform HR denial,
  catalog/role attributes, missing/invalid context and pool reuse. The migrated PostgreSQL API
  smoke executes existing API cross-tenant negatives; a test-only HTTP probe also asserts the
  request resolver's effective `current_user`, GUC and unfiltered RLS result for both tenants.
  Existing fast tests retain cache-prefix and worker-fake tenant/context mismatch denial. SQLite
  remains a useful no-op compatibility lane but is not accepted as RLS evidence.
- `TenantContext`, trusted tenant principal and legacy tenant-header parsing now reject zero UUIDs.
  F1C changes no route, OpenAPI operation, response model, auth/RBAC/audit contract, worker provider
  or business module.

#### F1C role provisioning contract

- Runtime must connect as a non-owner, `NOINHERIT` gateway login allowed to assume only the two
  capability roles. Migration/table-owner credentials are not an HTTP runtime path.
- Alembic creates or hardens the cluster-global NOLOGIN capability roles idempotently. Downgrade
  removes this database's grants, policies and RLS flags but intentionally retains shared roles.
  A reused capability that is itself member of any parent role fails upgrade preflight, preventing
  an inherited or `SET ROLE` path to broader database privileges.
- Local demo/smoke cross-tenant fixture setup is an explicit test/bootstrap admin connection; it
  never reuses the platform request session as an HR bypass.

### Historical F1B immutable request context, correlation and API contract standards

- Adds a canonical `frozen=True, slots=True` `RequestContext` carrying validated request/trace IDs,
  optional immutable tenant, actor/session placeholders, typed authentication strength and optional
  support-session metadata. Route/service code cannot mutate it; trusted dependencies derive a new
  instance while request and trace IDs remain invariant.
- The global HTTP middleware accepts or generates a safe opaque `X-Request-Id` (maximum 128) and a
  non-zero lowercase 32-hex `X-Trace-Id`. `X-Correlation-Id` is a deprecated alias of request ID.
  Missing IDs are generated; invalid, repeated, conflicting, e-mail/PII-shaped and JWT-shaped input
  is replaced and never reflected into response/error/log metadata.
- Every HTTP response carries exactly one canonical `X-Request-Id`, `X-Trace-Id` and deprecated
  `X-Correlation-Id`. Safe completion logs contain only allowlisted request/trace, authentication
  strength, optional tenant/support-session IDs and method/status; actor ID, end-user session ID,
  support-operator actor ID, tenant slug, PII, secrets and raw authorization material are excluded.
- The seven F1A platform/tenant success operations intentionally migrate to `{data,meta}`. Single
  response metadata is exactly `request_id`, `trace_id`, `correlation_id`; platform-list metadata
  also carries bounded `limit` and nullable `next_cursor`. Both aliases equal request ID.
- `GET /api/v1/platform/tenants` is now cursor-only: `limit` defaults to `50`, is bounded `1..200`,
  and the opaque keyset cursor follows deterministic `(created_at asc, id asc)` ordering. `offset`,
  malformed/repeated cursor, and repeated limit are rejected with the platform validation contract.
- Existing Phase-0 employee and leave-request lists remain plain arrays through the explicit
  compatibility adapter, return continuation in `X-Next-Cursor`, and retain bounded deprecated
  `offset`. Other Phase-0 response shapes are not silently enveloped. Their error-body correlation
  compatibility is also explicit while safe canonical response headers are universal.
- F1B introduced optional request-derived worker propagation with a fixed JSON-safe allowlist and
  validates request/trace, tenant/job equality, UUID placeholders and authentication strength.
  Every job tenant remains mandatory; F1E adds explicit `JobOrigin.REQUEST|SYSTEM`, requires context
  for request-origin jobs, forbids it for system jobs, and makes both A→B and B→A mismatch evidence
  explicit without claiming that the recording fake is a broker or authorization adapter.
  Extra/free-text metadata, tenant slug and raw auth material cannot enter serialized context.
- Generated OpenAPI documents the seven envelopes, correlation response headers, cursor-only
  platform list and Phase-0 compatibility/deprecation behavior. Smoke covers header propagation,
  unsafe-input non-reflection, envelope/meta equality, deterministic platform cursor traversal and
  unchanged employee/leave list bodies. No schema or Alembic migration is added.
- F1B does not implement authentication/session verification, RBAC/permission enforcement, audit
  persistence, PostgreSQL RLS, a real worker/broker, feature flags or a new product module.

#### F1B OpenAPI compatibility decision

- The operation registry remains 21 generated operations plus runtime `/openapi.json`; F1B changes
  contracts on the seven F1A success operations rather than adding a new endpoint.
- That change is intentional: new Phase-1 operations adopt `{data,meta}`, while historical Phase-0
  employee/leave success schemas stay unchanged. Tests separately assert both sides of the boundary.
- Platform list query parameters are exactly `limit` and `cursor`; page continuation is
  `meta.next_cursor`. All seven operations document the three safe correlation response headers.

### Historical F1A tenant lifecycle, typed settings and platform provisioning

- Adds exactly seven visible operations:
  `POST/GET /api/v1/platform/tenants`,
  `GET/PATCH /api/v1/platform/tenants/{tenant_id}`,
  `GET /api/v1/tenant` and
  `GET/PATCH /api/v1/tenant/settings`. `/api/v1/tenant/features` is not part of F1A.
- Platform routes require immutable injected `PlatformPrincipal(source)` and tenant routes require
  immutable injected `TenantPrincipal(tenant_id, source)`. The default dependencies
  `app.api.dependencies.get_platform_principal` and `get_tenant_principal` deny with `403`; tests
  may override them until Phase 2 auth exists. Caller-supplied header, path, query, body user ID or
  tenant ID never grants authorization.
- Provisioning creates server-owned UUID/status `provisioning` plus a fixed-column settings row in
  one Unit of Work. Canonical new input catalogs are plan `core|professional|enterprise`, region
  `tr-1|eu-1`, locale `tr-TR|en-US` and a recognized IANA timezone. Region is mutable only while
  provisioning; legacy `premium` plan rows remain readable but cannot be created/updated and are
  not rewritten by migration.
- Settings accept only `locale`, `timezone`, `week_start_day`, `date_format`, `time_format`.
  `tenant_settings` contains fixed columns, named checks and a tenant PK/FK; no arbitrary JSON,
  feature configuration, legal entity or customer business payload is introduced.
- Lifecycle graph and access are explicit: provisioning is platform-only; trial/active read-write;
  suspended/offboarding read-only; closed denied. Same-state updates are no-op and only the
  transition graph documented in ADR-017 is accepted. Tenant access returns `423` for provisioning,
  `410` for closed, and settings PATCH returns `423` for suspended/offboarding.
- Platform list/detail expose exactly tenant metadata, plan, region, locale/timezone, timestamps and
  lifecycle-derived health (`provisioning|healthy|restricted|offboarding|closed`). They do not join,
  count or return employee, user, leave, document or other HR data.
- At the F1A checkpoint, success responses were direct typed object/list. F1B supersedes that
  temporary decision for exactly these seven operations with the explicit migration above; this
  historical statement must not be read as current runtime behavior.
- F1A does not implement auth/session/RBAC, audit persistence/recorder, PostgreSQL RLS, feature
  flags, support access, legal entity, payroll, SGK, banking, PDKS, AI or external integrations.
- Migration `0013_tenant_settings` is additive and backfills default settings for existing tenants.
  Downgrade refuses to discard any non-default typed setting, reports
  `custom_tenant_settings=<count>`, and proceeds only for default-only rows. SQLite/PostgreSQL
  round-trip/refusal, native constraint, schema-drift and tenant-root FK evidence passed. No commit
  SHA is recorded until the verified worktree is committed.

#### Historical F1A OpenAPI compatibility decision

- The contract delta is additive: Phase-0's 14 generated operations remain, and F1A adds seven for
  21 generated operations plus runtime `/openapi.json` in the 22-row documented table.
- Platform read fields are exactly `id`, `slug`, `name`, `status`, `plan_code`, `data_region`,
  `locale`, `timezone`, `health`, `created_at`, `updated_at`. Tenant current and settings field sets
  are the narrower exact shapes recorded in the endpoint draft.
- These operations did not adopt the envelope at the F1A checkpoint. F1B now owns the intentional
  envelope/header/pagination diff; the historical F1A and Phase-0 evidence remains preserved rather
  than silently rewritten.

### Historical P0G architecture gate and review checkpoint

- Re-ran the fast SQLite, real PostgreSQL 16.4 checkpoint, Ruff and local API smoke gates. The
  2026-07-11 continuation also re-ran the complete and focused PostgreSQL lanes on 17.10, satisfying
  the project's PostgreSQL 16+ contract. Focused commands separately cover Alembic round-trip/drift,
  OpenAPI, import boundaries, direct-DB tenant negative writes, concurrency/idempotency and
  query-plan behavior.
- Found and repaired a PostgreSQL test-order defect that a lucky collection order could hide. The
  PostgreSQL API smoke leaves intentionally retained archive/idempotency rows; a later P0D fixture
  could then be correctly refused by the `0011` downgrade preflight. Every `postgres` test now gets
  its own uniquely named disposable database, so all migration tests are independent of collection
  order and retained data from another test.
- Closed the literal no-service-commit gate. `seed_demo_data` now flushes only; the standalone local
  script owns the atomic transaction with `session_factory.begin()`. An AST architecture regression
  rejects `commit()` or `rollback()` anywhere under `backend/app/services`.
- Completed the Phase-0 worker spike without installing a provider: ADR-008 selects Dramatiq 2.2 +
  Redis as the later runtime adapter and records the comparison. `app.platform.workers` contains
  only a narrow tenant-aware job envelope/queue port and deterministic recording fake. No broker,
  worker process, schedule, deployment or external integration was added.
- Added the persisted Phase-0 OpenAPI contract manifest. It hashes every complete generated
  operation, every component schema and top-level metadata, while existing tests/smoke continue to
  lock readable metadata, the exact operation registry, documentation-table parity and runtime
  endpoint execution.
- The final documentation audit synchronized ADR-015 and the ERD with the implemented
  command/target/body idempotency fingerprint, exposed the canonical `platform/` and `modules/`
  skeleton in README, and corrected the historical risk checklist to say CI is template-only.
- No Phase-1 API, auth, RBAC, RLS, audit/outbox, new product module, payroll, SGK, banking, PDKS,
  AI, external integration, deploy, staging or cron behavior was started.

#### Historical Phase-0 OpenAPI compatibility decision

Generated OpenAPI was compared with the Phase-0 base commit `80b2768` and frozen at this review
checkpoint:

- generated operations remain **14 → 14**, with no added or removed path/method; the documentation
  count is 15 only because runtime `/openapi.json` is included;
- there are no component-schema, request-body or successful response-body schema changes;
- intentional additive changes are optional `cursor` parameters plus `X-Next-Cursor` on the two
  list operations, optional `X-Idempotency-Key` and documented 400/409 responses on five critical
  POST operations, and documented 409 responses on employee PATCH/DELETE;
- both existing `offset` parameters remain optional compatibility paths but are now marked
  deprecated; list descriptions were updated to prefer keyset pagination;
- the one intentional semantic change is employee DELETE becoming retention-safe archive while
  preserving the path and `204` response; its summary/description now say archive. ADR-015,
  README, endpoint draft and smoke all document and test it;
- the Phase-1 `{data, meta}` envelope, auth-derived tenant/actor, RBAC and RLS remain absent.

The checked manifest is `backend/tests/contracts/phase0_openapi_contract.json`. Future intentional
contract work must update that manifest and its migration/deprecation note in the same review.

The historical comparison was reproduced from detached `80b2768` and current worktrees by
generating normalized schemas with the same environment:

```bash
repo_root="$(pwd)"
base_dir="$(mktemp -d)"
git worktree add --detach "$base_dir" 80b2768
(cd "$base_dir" && PYTHONPATH=backend "$repo_root/.venv/bin/python" -c \
  'import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))') \
  > /tmp/phase0-base-openapi.json
PYTHONPATH=backend "$repo_root/.venv/bin/python" -c \
  'import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))' \
  > /tmp/phase0-head-openapi.json
git diff --no-index --stat -- /tmp/phase0-base-openapi.json /tmp/phase0-head-openapi.json
git worktree remove "$base_dir"
```

The expected non-zero diff was reviewed operation/component-wise. Result: 14 → 14 operations,
exactly nine changed operation documents, no component/request/success-body schema change, and only
the intentional differences enumerated above. The manifest test separately proves current
generated OpenAPI equals the reviewed P0G snapshot.

#### Historical review-only plan deviations

The enumerated Phase-0 architecture gate below is locally green. The following broader master-plan
items are incomplete or only partially evidenced and require Murat's explicit disposition before
Phase 1:

- global request/transaction correlation and PII-safe slow-query logging;
- active CI workflow activation. The repository contains only
  `docs/09-uygulama/templates/backend-ci.yml`, not `.github/workflows/*`;
- HTTP endpoint response-time/p95 characterization. P0F records query counts and PostgreSQL
  `EXPLAIN (ANALYZE, BUFFERS)` timings, but deliberately does not treat them as an end-to-end
  response-time profile;
- migration of one real product module into the target modular-monolith packages. The boundary
  skeleton and enforcement gate are active, while employee and leave code remain in the documented
  legacy compatibility area;
- the common mutation audit-event expectation and a combined domain-write plus audit/outbox
  rollback proof. Current fresh-session tests prove domain write rollback, but no audit/outbox
  recorder or mutation audit-event suite is implemented in Phase 0;
- an explicit connection-leak stress/regression gate. Lifespan engine disposal and rollback after
  errors are covered, but leak behavior is not separately load-tested.

The user-email strategy is now decided but intentionally not migrated early: current
`users(tenant_id, email)` remains case-sensitive; before auth, an explicit
`lower(btrim(email))` normalized column/index will be introduced rather than `citext`.

#### Historical P0G verification matrix

Final commands and results are recorded here after the complete P0G rerun:

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed, `All checks passed!` |
| Fast SQLite | `uv run pytest -q` | Passed, 436 tests; 17 PostgreSQL tests deselected; one known Starlette warning |
| PostgreSQL 16+ | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed at the 16.4 checkpoint and again on 17.10 during continuation: 17 tests; 436 fast tests deselected |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed, `BACKEND_SMOKE_OK`, all 15 documented endpoints executed |
| OpenAPI + imports | `uv run pytest -q backend/tests/test_openapi_contract.py backend/tests/test_openapi_metadata.py backend/tests/test_import_boundaries.py` | Passed, 39 tests |
| SQLite migrations | `uv run pytest -q backend/tests/test_migrations.py` | Passed, 22 tests |
| PostgreSQL migration/runtime | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_baseline.py` | Passed, 5 tests: round-trip, drift, native constraints, runtime timeouts, API smoke |
| Direct-DB tenant negatives | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_tenant_relational_integrity.py` | Passed, 5 tests covering all current composite tenant relationships and expand-contract behavior |
| PostgreSQL concurrency | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_command_transactions.py backend/tests/integration/test_postgresql_p0e_concurrency.py` | Passed, 6 tests: duplicate winner/mapping, lock mapping, one terminal decision, same-key replay, retention, downgrade refusal |
| Query-plan baseline | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_p0f_performance.py` | Passed, 1 test with 10k employee/5k leave EXPLAIN assertions |
| Git hygiene | Exact commands below | Passed: no whitespace errors, prohibited path changes or secret-pattern matches across 23 P0G files; clean status verified after commit |

The final continuation resumed from clean checkpoint `c9c99c9` and reproduced the matrix before
this documentation-only sync: the fast lane passed 436 tests with 17 deselected; the complete
PostgreSQL 17.10 lane passed 17 tests with 436 deselected; and the focused OpenAPI/import, SQLite
migration, PostgreSQL baseline, tenant-integrity, concurrency and query-plan commands passed
39, 22, 5, 5, 6 and 1 tests respectively. Ruff and `BACKEND_SMOKE_OK` also passed at the same
checkpoint. No runtime, migration or OpenAPI artifact changed during the final documentation sync.

The continuation explicitly reversed the PostgreSQL test-file order to verify that the function-scope
database isolation does not depend on the normal collection order:

```bash
IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres \
  backend/tests/integration/test_postgresql_tenant_relational_integrity.py \
  backend/tests/integration/test_postgresql_p0f_performance.py \
  backend/tests/integration/test_postgresql_p0e_concurrency.py \
  backend/tests/integration/test_postgresql_command_transactions.py \
  backend/tests/integration/test_postgresql_baseline.py
```

Result: passed, 17 tests on PostgreSQL 17.10. The normal full lane and the four focused PostgreSQL
commands in the matrix also passed in the same continuation environment.

The P0G hygiene audit is reproducible from the synchronized P0F commit through local P0G `HEAD`:

```bash
git diff --check 585fa0a..HEAD
test -z "$(git status --porcelain)"
if git diff --name-only 585fa0a..HEAD | \
  rg -i '(^|/)(\.env($|\.)|.*secret.*|.*credential.*|.*token.*|.*staging.*|.*cron.*|.*deploy.*|.*auth.*)'; then
  exit 1
fi
if git diff --format= --unified=0 585fa0a..HEAD | \
  rg -i '^\+.*(api[_-]?key|client[_-]?secret|access[_-]?token|private[_-]?key|password\s*[:=])'; then
  exit 1
fi
```

Result: all commands exited zero with no prohibited match; `git status --short --branch` showed only
the expected local commits ahead of the review-branch remote after the final commit.

### Historical P0F pagination, search and query-performance baseline

The bullets in this subsection preserve what P0F implemented and measured. P4A later superseded
the employee cursor only: the current directory uses `Employee.id ASC`, and the old employee-number
PostgreSQL plan evidence was not rerun or relabeled as repair evidence.

- Added versioned opaque keyset cursors to employee and leave-request high-growth lists while
  preserving their plain-array bodies and bounded `offset` compatibility path. A page that proves
  more rows exist returns `X-Next-Cursor`; positive `offset` cannot be combined with `cursor`.
- Employee ordering is `(employee_number asc, id asc)`. Leave ordering and cursor predicates use
  the complete mixed tuple `(created_at desc, start_date asc, id asc)`. Cursor values never replace
  the independent tenant predicate.
- Preserved case-insensitive literal substring `q` behavior for employee number/email, including
  literal SQL wildcards, while switching PostgreSQL to index-compatible `ILIKE`. Revision
  `0012_p0f_query_performance` adds non-archived `pg_trgm` GIN indexes for both fields.
- Replaced row-by-row `lower(trim(department))` filtering with stored generated
  `department_normalized` and `(tenant_id, department_normalized)`. Added the leave keyset index
  `(tenant_id, created_at desc, start_date asc, id asc)`.
- Consolidated four sequential dashboard count queries into one conditional aggregate with a
  tenant-scoped pending-leave scalar subquery. Measured query count is now 4 instead of 7 for the
  default summary, and 2 instead of 5 when activity is disabled.
- Added deterministic 10,000-employee + 5,000-leave PostgreSQL seed/`VACUUM (ANALYZE)` procedure
  and `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` regressions. Selective search proves both trigram
  indexes, employee cursor proves the tenant/employee-number unique index, and leave cursor proves
  the new composite index. Full-tenant dashboard aggregates may correctly use a sequential scan.
- Kept cache out of scope after measurement: no Redis/cache dependency, cache key, invalidation
  behavior, deployment, auth, Phase-1 envelope, audit stream, or unrelated feature was added.
- Reproduction and captured PostgreSQL 16.4 evidence are recorded in
  `docs/09-uygulama/12-phase-0-query-performance-baseline.md`.

### Historical P0E concurrency, idempotency and archive hardening

- Added database-backed, tenant-global command receipts for optional `X-Idempotency-Key` on
  employee create, leave request create, and leave approve/reject/cancel. The same semantic
  command/target/body replays the first successful response snapshot and resource ID; reusing the
  same tenant key for a different command, target, or body returns
  `409 idempotency_key_mismatch` without a second domain write.
- Receipt claim/completion and the domain write share the existing Unit of Work transaction.
  Failed commands roll back their incomplete receipt. The unique
  `uq_command_idempotency_tenant_key` constraint chooses one winner for concurrent claims; the
  loser reopens a clean transaction and replays the committed receipt.
- Keys are independent across tenants. Empty, whitespace-bearing, longer-than-128-character, or
  repeated headers return `400 idempotency_key_invalid`. No receipt TTL/cleanup job exists yet, so
  completed keys remain reserved while their tenant exists.
- Leave decisions now read the tenant-scoped request row with PostgreSQL `SELECT ... FOR UPDATE`
  inside the command transaction. Concurrent approve/reject/cancel operations therefore produce
  exactly one terminal winner; a different-key loser observes the committed terminal state and
  returns the existing `409 leave_request_transition_conflict`. An equivalent same-key retry
  replays the first successful decision snapshot.
- `DELETE /api/v1/employees/{employee_id}` keeps its path and `204` response but now archives by
  setting `archived_at`. Repeating DELETE is a no-op `204`. Normal list/detail/update, new leave,
  leave-balance, dashboard workforce, and employee-activity reads hide archived employees;
  employee number remains reserved and existing leave/balance history remains stored.
- Changed the leave-request and leave-balance employee composite FKs to `ON DELETE RESTRICT`, so
  direct employee deletion cannot cascade away history. There is no employee purge HTTP endpoint.
  Tenant-root graph deletion remains only a restricted retention/offboarding operation with
  explicit approval outside the normal employee command surface.
- Added Alembic revision `0011_p0e_concurrency_idempotency_archive`, fast SQLite command/API/model/
  migration regressions, local smoke replay/archive scenarios, and real PostgreSQL proofs for the
  leave one-winner race, concurrent same-key create, and retention-safe employee archive.
- `0011` downgrade refuses to discard non-null archive markers or idempotency receipts until an
  operator explicitly exports/remediates that retained state; SQLite and PostgreSQL regressions
  prove the failed downgrade leaves the head revision and retained rows intact.
- P0E adds no auth/RBAC/RLS, audit/outbox, worker/TTL cleanup, payroll/bordro, SGK, banking, PDKS,
  AI, external integration, deployment, or new product module.

### Historical P0D tenant relational integrity

- At the P0D checkpoint, inventoried every then-implemented foreign key. Root ownership references
  from `users`, `employees`, `leave_requests`, and `leave_balance_summaries` to `tenants.id` remain
  scalar; the four employee/user references owned by leave tables now include the child tenant.
  P0E later added `command_idempotency.tenant_id → tenants.id` as another scalar root-ownership
  relationship; it does not reference a tenant-owned child resource.
- Added `(tenant_id, id)` candidate keys to the only currently referenced tenant-owned parents,
  `employees` and `users`.
- Replaced tenant-owned scalar references with named composite foreign keys for leave request
  employee/requester/decider and leave balance employee. P0E current head keeps requester/decider
  `NO ACTION` and nullable decider `MATCH SIMPLE`, while employee history relationships are now
  `RESTRICT` rather than destructive cascade.
- Added a two-revision expand-contract migration. `0009` runs a reusable preflight query across all
  eight implemented relationships, builds resumable PostgreSQL candidate indexes concurrently,
  adds composite FKs `NOT VALID` while legacy FKs remain, and repeats the preflight under the new
  constraint locks to close the concurrent-index write window. `0010` validates the new constraints
  before dropping only the four legacy employee/user scalar FKs.
- Downgrade restores and validates legacy FKs before composite FKs and candidate keys are removed.
  Valid-data migration round-trip tests preserve existing leave rows.
- Added real PostgreSQL tests that identify orphan/cross-tenant preflight rows, assert exact
  candidate/composite constraint definitions and validation state, and bypass application services
  to reject every cross-tenant relationship by its named composite constraint.
- Kept SQLite as fast model/migration/API compatibility coverage only; it is not evidence for
  PostgreSQL concurrent index, `NOT VALID`, validation, or direct-write behavior.
- P0D changed no endpoint, OpenAPI schema, response/error contract, auth/RBAC behavior, or product
  feature. Existing application tenant guards remain; F1C later adds PostgreSQL RLS without
  rewriting this historical composite-FK migration.

### Historical P0C transaction and error boundary

- Added `SqlAlchemyUnitOfWork.execute` as the sole begin/commit/rollback owner for the transitional
  `EmployeeCommandHandler` and `LeaveRequestCommandHandler` write paths.
- Employee create/update/archive (the compatible DELETE path) and leave request
  create/approve/reject/cancel run through those application command handlers. The underlying
  business services may `flush()` so constraints and generated values are visible, but migrated
  service methods never `commit()` independently.
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
- P0C itself did not implement leave decision locking or idempotency; P0E now composes both on that
  unchanged transaction boundary. P0D supplies composite tenant foreign keys, and P0E changes only
  the employee-history delete action to retention-safe `RESTRICT`.
- No endpoint path, method, success response shape, tenant isolation rule, auth/RBAC behavior, or
  product feature changes. The only new HTTP outcomes are safe stable mappings for persistence
  failures that previously could escape as internal errors.

### Historical preserved P0A/P0B foundation

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
| POST | `/api/v1/platform/tenants` | P3K verified | Separate `PlatformBearerAuth` + live platform session; server-owned status/ID and typed settings/configured limit |
| GET | `/api/v1/platform/tenants` | P3K verified | Separate `PlatformBearerAuth`; bounded cursor and projected lifecycle/plan/configured-limit metadata with no HR payload/count |
| GET | `/api/v1/platform/tenants/{tenant_id}` | P3K verified | Separate `PlatformBearerAuth`; platform-safe metadata/plan/region/health/configured limit only |
| PATCH | `/api/v1/platform/tenants/{tenant_id}` | P3K verified | Separate `PlatformBearerAuth`; typed metadata/plan/limit and hardened terminal lifecycle transitions |
| GET | `/api/v1/platform/tenants/{tenant_id}/features` | P3K verified | Separate `PlatformBearerAuth`; fixed effective feature catalog and no HR data/usage |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/features` | P3K verified | Separate `PlatformBearerAuth`; unique typed keys, lifecycle guard and redacted actual-change events |
| GET | `/api/v1/tenant` | Implemented and verified | `{data,meta}`, injected tenant-principal metadata and lifecycle access guard |
| GET | `/api/v1/tenant/settings` | Implemented and verified | `{data,meta}`, exact five-key typed settings view and tenant isolation |
| PATCH | `/api/v1/tenant/settings` | Implemented and verified | `{data,meta}`, exact allowlist update and suspended/offboarding read-only guard |
| GET | `/api/v1/tenant/features` | Implemented and verified | Current-principal-only ordered effective flags; no tenant selector or mutation |
| POST | `/api/v1/platform/auth/login` | Implemented for P3D | Global email/password verification followed by active platform-role enforcement; no tenant or organization selection; separate cookie/audience |
| POST | `/api/v1/platform/auth/refresh` | Implemented for P3D | Platform-cookie-only tenantless family rotation and reuse detection |
| POST | `/api/v1/platform/auth/logout` | Implemented for P3D | Revokes only the platform family and clears only the platform cookie |
| GET | `/api/v1/platform/me` | Implemented for P3D | `PlatformBearerAuth` plus active tenantless session/role/version validation; no tenant-shaped principal fields |
| POST | `/api/v1/auth/login` | Implemented for P3B | Email/password-only global credential verification, post-verification membership discovery, and either direct session or opaque organization-selection response |
| POST | `/api/v1/auth/select-organization` | Implemented for P3C | One-use opaque selection consumption and membership/tenant-bound access plus refresh session issuance |
| POST | `/api/v1/auth/organization-selection` | Implemented for P3C | Authenticated identity-derived alternatives, source-family revocation, and no caller tenant selector |
| POST | `/api/v1/auth/refresh` | Implemented for F2B | Single-use rotation, retained token history, reuse-triggered family revoke, and rotated HttpOnly cookie |
| POST | `/api/v1/auth/logout` | Implemented for F2B | Idempotent family revoke and exact-policy refresh-cookie deletion |
| GET | `/api/v1/me` | Implemented for F2D | Bearer plus active server-session/version validation; current user, tenant, roles and permissions derived without caller selectors |
| POST | `/api/v1/auth/activate` | Completed for P3E | One-use hashed invitation; first-password setup or current-password proof that activates only an existing identity's pending membership |
| POST | `/api/v1/auth/password-reset/request` | Implemented for P3E | Enumeration-resistant `202 accepted`, separate delivery, no identity/organization/token response |
| POST | `/api/v1/auth/password-reset/confirm` | Implemented for P3E | One-use hashed reset, global credential reconciliation and all-realm session invalidation |
| POST | `/api/v1/users/invitations` | Implemented for F2D | Bearer-derived actor/tenant, exact invite permission and header/payload tenant-spoof resistance |
| GET | `/api/v1/users` | Implemented for F2D | Permission-protected tenant list with role summaries, bounded cursor and indexed filters |
| GET | `/api/v1/users/{user_id}` | Implemented for F2D | Permission-protected tenant detail with roles and identical missing/cross-tenant behavior |
| PATCH | `/api/v1/users/{user_id}` | Implemented for F2D | Permission-protected full-name/status allowlist and credential revocation on lock/disable |
| GET | `/api/v1/roles` | Implemented for F2D | Seeded tenant-assignable roles with explicit permission codes; platform role excluded |
| GET | `/api/v1/permissions` | Implemented for F2D | Seeded tenant permission catalog; platform permissions excluded |
| PUT | `/api/v1/users/{user_id}/roles` | Implemented for F2D | Atomic replace semantics, tenant isolation, platform-role rejection and permission-version bump |
| GET | `/api/v1/audit-events` | Implemented for F2E | Bearer + tenant audit permission, role/category filtering, redacted cursor page |
| GET | `/api/v1/audit-events/{event_id}` | Implemented for F2E | Read-only safe detail with identical hidden/cross-tenant not-found behavior |
| GET | `/api/v1/platform/audit-events` | Implemented for F2E/P3D | Separate `PlatformBearerAuth`, live platform session, and platform-operations-only projection |
| GET | `/api/v1/legal-entities` | Implemented for P3F | Current-tenant bounded cursor list, stable codes and default marker |
| POST | `/api/v1/legal-entities` | Implemented for P3F | Tenant-unique stable code, active create and same-transaction audit |
| GET | `/api/v1/legal-entities/{legal_entity_id}` | Implemented for P3F | Current-tenant detail with indistinguishable missing/cross-tenant `404` |
| PATCH | `/api/v1/legal-entities/{legal_entity_id}` | Implemented for P3F | Allowlisted legal settings; stable code/default marker immutable and lifecycle guarded |
| GET | `/api/v1/branches` | Implemented for P3F | Bounded cursor list with legal-entity/status-bound continuation and archived history |
| POST | `/api/v1/branches` | Implemented for P3F | Active legal-entity guard, IANA timezone, stable tenant-wide code and audit |
| GET | `/api/v1/branches/{branch_id}` | Implemented for P3F | Active or archived current-tenant branch detail |
| PATCH | `/api/v1/branches/{branch_id}` | Implemented for P3F | Active-only allowlisted location update; code and legal-entity binding immutable |
| DELETE | `/api/v1/branches/{branch_id}` | Implemented for P3F | Terminal archive keeps history/code and closes new assignments |
| GET | `/api/v1/departments` | Implemented for P3G | Current-tenant active/archive list with stable-code cursor and bounded pages |
| POST | `/api/v1/departments` | Implemented for P3G | Active root/child create with immutable tenant-unique code, parent guard and atomic audit |
| GET | `/api/v1/departments/tree` | Implemented for P3G | One bounded root or direct-child level per request; cursor bound to parent/archive filters |
| GET | `/api/v1/departments/{department_id}` | Implemented for P3G | Active or archived current-tenant detail with retained parent history |
| PATCH | `/api/v1/departments/{department_id}` | Implemented for P3G | Active-only rename/safe move; application and PostgreSQL cycle prevention |
| DELETE | `/api/v1/departments/{department_id}` | Implemented for P3G | Terminal archive rejects active children and retains stable code/parent history |
| GET | `/api/v1/positions` | Implemented for P3H | Current-tenant active/archive catalog with bounded status/search-bound cursor pages |
| POST | `/api/v1/positions` | Implemented for P3H | Reusable active job title with tenant-unique stable code and same-transaction audit |
| GET | `/api/v1/positions/{position_id}` | Implemented for P3H | Active or archived current-tenant detail with identical missing/cross-tenant `404` |
| PATCH | `/api/v1/positions/{position_id}` | Implemented for P3H | Active-only title update while stable code remains immutable |
| DELETE | `/api/v1/positions/{position_id}` | Implemented for P3H | Terminal archive preserves code/history and closes new assignments |
| GET | `/api/v1/employee-assignments` | Implemented for P3I | HR-only bounded current/history view with employee filter and structured organization labels |
| POST | `/api/v1/employee-assignments` | Implemented for P3I | First effective-dated structured assignment with active-reference validation and atomic audit |
| GET | `/api/v1/employee-assignments/options` | Implemented for P3I | Bounded active employee and team-capable manager choices for the HR form |
| GET | `/api/v1/employee-assignments/{assignment_id}` | Implemented for P3I | Current or retained historical assignment within authenticated tenant HR scope |
| PATCH | `/api/v1/employee-assignments/{assignment_id}` | Implemented for P3I | Closes the open interval and appends an immutable successor plus reporting-line audit |
| GET | `/api/v1/teams/me` | Implemented for P3I | Authenticated manager's current direct team derived only from structured assignments |
| GET | `/api/v1/org-chart` | Implemented for P3J | Organization-read protected bounded root/direct-report pages with parent-bound cursor and resolved labels |
| GET | `/api/v1/dashboard/summary` | P3K verified | Live tenant `BearerAuth` + `dashboard:read:tenant`; bounded tenant metrics; headers cannot select scope |
| GET | `/api/v1/employees` | P4A implemented | Live tenant `BearerAuth` + `employee:read:tenant`; bounded cursor, full-name/identity/status/current-assignment filters and batched assignment summary |
| POST | `/api/v1/employees` | P4A implemented | `employee:update:tenant`; minimal HR create, normalized number/work-email conflicts, optional tenant-global idempotent replay and audit |
| GET | `/api/v1/employees/{employee_id}` | P4A implemented | `employee:read:tenant`; active summary with additive version/current assignment and indistinguishable cross-tenant `404` |
| PATCH | `/api/v1/employees/{employee_id}` | P4A implemented | `employee:update:tenant`; compatible partial update plus optional optimistic version and actual-change audit |
| DELETE | `/api/v1/employees/{employee_id}` | P4A implemented | `employee:update:tenant`; idempotent archive, retained history and first-transition audit |
| GET | `/api/v1/employees/{employee_id}/profile` | P4B implemented | `employee:read:tenant`; `{data,meta}` core/personal/employment aggregate plus bounded Phase 3 current assignment/history, separate section versions and no-store response |
| PATCH | `/api/v1/employees/{employee_id}/profile/personal` | P4B implemented | `employee:update:tenant`; mandatory personal version, conditional employee version for core fields, atomic allowlisted update/audit and stale `409` |
| PATCH | `/api/v1/employees/{employee_id}/profile/employment` | P4B implemented | `employee:update:tenant`; mandatory employment version, conditional employee version for start date, no lifecycle or assignment mutation |
| GET | `/api/v1/employees/{employee_id}/leave-balances` | P3K verified | `leave:read:tenant`; active-employee manual summaries and cross-tenant hiding |
| GET | `/api/v1/leave-requests` | P3K verified | `leave:read:tenant`; tenant filters, mixed-order cursor and deprecated offset compatibility |
| POST | `/api/v1/leave-requests` | P3K verified | HR-only `leave:manage:tenant`; pending create, tenant validation and optional replay |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | P3K verified | HR-only `leave:manage:tenant`; row-lock one-winner, pending-only transition and replay |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | P3K verified | HR-only `leave:manage:tenant`; row-lock one-winner, pending-only transition and replay |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | P3K verified | HR-only `leave:manage:tenant`; row-lock one-winner, pending-only transition and replay |

F2D adds role, permission and exact user-role replacement operations; F2E adds tenant audit
list/detail and the separate platform audit list. P3C adds two organization-selection operations,
P3D adds four platform-auth operations, P3E adds two password-recovery operations, P3F adds
nine legal-entity/branch operations, P3G adds six department operations and P3H adds five position
catalog operations. P3I adds six assignment/team operations and P3J adds the lazy org-chart read,
bringing the Phase 3 surface to 74 generated operations and 75 documented runtime endpoints
including `/openapi.json`. P3K changes the authority metadata and enforcement of twelve historical
operations without adding a route. P4A changes no route count; P4B adds the three Employee 360
operations above, so the current surface is 77 generated operations and 78 documented runtime
endpoints. The executable smoke covers email-only login, multi-org
selection, platform/tenant realm separation, organization administration, assignment/team/chart
flows, legacy HR authorization and contract-table drift without printing credential material.

## Current Behavior Notes

- Every HTTP request has an immutable request context. Request and trace IDs are validated/generated
  once and emitted as `X-Request-Id`, `X-Trace-Id`, plus deprecated request-ID alias
  `X-Correlation-Id`; response body meta on new Phase-1 operations comes from that same context.
  Duplicate/conflicting/unsafe inputs are regenerated and not reflected or logged.
- Request-context error metadata is limited to request/trace. Completion-log metadata excludes
  actor/session/support-operator IDs, tenant slug, raw auth, tokens, secrets and PII. F2 bearer
  validation derives tenant, actor, live session, authentication strength and permission version
  into a new immutable context; caller headers/body cannot populate those authority fields.
- F2B access credentials are short-lived and session-bound. Refresh credentials exist only in a
  host-only HttpOnly cookie and as SHA-256 hashes in tenant-RLS tables. Rotation consumes one token;
  presenting it again commits revocation of its entire fixed-expiry family. Logout revokes that
  family, and `/api/v1/me` revalidates family, user and tenant state rather than trusting headers.
- Historical trusted-principal compatibility seams still deny by default when no principal is
  injected. All browser-facing protected routes use live server sessions: tenant routes require
  `BearerAuth`, platform routes require the separate `PlatformBearerAuth`, and no
  header/body/path/query field constructs authority or chooses the current tenant. P3K migrated
  the last twelve dashboard/employee/leave operations away from tenant-header authorization.
- Platform create accepts only `slug`, `name`, canonical optional `plan_code`, `data_region`,
  `locale`, IANA `timezone`, nested `settings` containing week/date/time formats and optional nested
  `limits.active_employees`. The server owns UUID and initial `provisioning` status. Duplicate slug
  returns `409 tenant_slug_conflict`.
- Platform PATCH accepts only `name`, `status`, `plan_code`, `data_region`, `locale`, `timezone` and
  nested configured limit; slug/id/extra/null/empty changes are rejected. Same-state is a no-op. Invalid transitions,
  post-provisioning region relocation, closed metadata mutation, and offboarding non-closure
  mutation return `409 tenant_lifecycle_conflict`. Transition to offboarding/closed cannot be
  combined with metadata/limit mutation in the same command.
- Platform response `data` has an exact safe schema: `id`, `slug`, `name`, `status`, `plan_code`,
  `data_region`, `locale`, `timezone`, `health`, nested `limits.active_employees`, `created_at`,
  `updated_at`. The bounded list uses
  `limit` default `50`, range `1..200`, and opaque cursor ordered by `created_at asc, id asc`;
  continuation is `meta.next_cursor`, and offset is rejected. Health is a pure lifecycle mapping;
  configured limit is not an employee usage count. Dedicated platform query code explicitly
  projects `tenants` columns and does not query/join employee, user, leave or document data.
- `plan_code` response parsing recognizes pre-F1A `premium` rows solely for read compatibility.
  Create/PATCH catalogs remain canonical and cannot write `premium`; `0013` does not reinterpret
  stored legacy plan values.
- Tenant current has exactly `id`, `slug`, `name`, `status`, `plan_code`, `locale`, `timezone`.
  Tenant settings has exactly `locale`, `timezone`, `week_start_day`, `date_format`, `time_format`.
  Typed allowlists are locale `tr-TR|en-US`, week `monday|sunday`, date
  `DD.MM.YYYY|MM/DD/YYYY|YYYY-MM-DD`, time `24h|12h`; timezone uses the IANA catalog. Arbitrary
  payloads, explicit nulls and empty PATCH bodies fail validation.
- Lifecycle access is deterministic. Provisioning tenant endpoints return `423 tenant_not_ready`;
  closed returns `410 tenant_closed`; suspended/offboarding GETs remain available while settings
  PATCH returns `423 tenant_read_only`. Trial/active are read-write. Platform health maps these
  states to `provisioning`, `healthy`, `restricted`, `offboarding`, `closed`.
- Feature reads always return `organization`, `employees`, `documents`, `leave`, `self_service`,
  `reporting`, `notifications` in that order. Defaults are true only for employees/leave/reporting;
  each item reports effective boolean and `default|override` source. Platform PATCH accepts a
  non-empty unique subset of typed keys with strict booleans; tenant feature API is read-only and
  scopes exclusively from the injected principal.
- Tenant principal injection alone still yields `403 platform_access_denied` on platform feature
  and tenant-operations routes. Header/query/body/path tenant or user identifiers never promote it.
- Actual create/status/setting/flag changes and F2 auth/user/role/session commands produce exact
  allowlisted redacted event contracts inside the command UoW. No-op and failed commands emit none.
  F2 installs the same-session append-only recorder and separate tenant/platform read policies;
  normal runtime capability cannot update or delete audit rows.
- The seven F1A success operations now use the F1B `{data,meta}` contract. Existing Phase-0
  employee/leave response bodies remain direct schema/list; employee and leave-request lists use
  the explicit plain-array + `X-Next-Cursor` adapter and retain deprecated offset compatibility.
- Protected domain endpoints require the appropriate bearer credential and derive the immutable
  tenant from its live session. `X-Tenant-Id` and `X-Tenant-Slug` are not selector parameters;
  absent, duplicated, malformed or cross-tenant values do not change an authenticated request's
  tenant and cannot authorize a request without a valid tenant session.
- Employee create, leave request create, and leave approve/reject/cancel accept an optional
  `X-Idempotency-Key`. The key is tenant-global: equivalent semantic retries replay the first
  successful snapshot, while a changed command, target, or body returns
  `409 idempotency_key_mismatch` without a second write. Same key values in different tenants are
  independent. No TTL/cleanup is active.
- Historical W4B4 header validation remains covered only as compatibility evidence. The active P3K
  authority boundary authenticates before domain processing: no bearer returns `401`, a valid
  tenant session without the exact permission returns `403 authorization_denied`, and a platform
  token cannot be interpreted as a tenant token.
- Employee list supports `department`, `status`, `q`, `limit`, deterministic `cursor`, and the
  deprecated `offset` compatibility path. Filters and archive visibility are tenant-scoped before
  pagination. `limit` defaults to `50` and is capped at `200`; another page is exposed only through
  `X-Next-Cursor` after a `limit + 1` probe. The opaque cursor payload is only `id: UUID`; current
  ordering is `Employee.id ASC` with the exact predicate `Employee.id > cursor.id`. Strict extra
  rejection makes old `employee_number` and `created_at` cursor payloads invalid. There is no
  datetime normalization or dialect-specific `julianday` path.
- Employee lifecycle validation is active: `terminated` requires `employment_end_date`; `active`
  and `on_leave` require `employment_end_date: null`. Violations return
  `employee_invalid_lifecycle`, and the database also has
  `ck_employees_lifecycle_status_dates`.
- Employee DELETE is an idempotent archive command: the first call sets `archived_at`, and repeat
  calls preserve it and return `204`. Normal employee list/detail/update, new leave request,
  leave-balance, dashboard workforce/count/distribution/new-starter, and employee-activity reads
  exclude archived rows. The employee row, employee number, and existing leave/balance history are
  retained; historical leave list/activity remains available within its tenant.
- Leave request list supports `status`, `employee_id`, inclusive overlapping `start_date` and
  `end_date` filters, plus bounded `limit`, deterministic `cursor`, and deprecated `offset`
  compatibility. Ordering/cursor fields are `created_at desc`, `start_date asc`, and `id asc`.
- Leave request decision endpoints approve, reject, or cancel only pending requests and require the
  deciding user to belong to the same tenant. The tenant-scoped row is locked through the command
  transaction. Concurrent contradictory decisions have exactly one success; the loser receives
  the stable transition conflict. Equivalent keyed retries replay the first successful terminal
  response rather than re-running the transition.
- Dashboard summary is DB-backed, tenant-scoped, and bounded to four SELECT statements with normal
  recent activity (two without activity). It returns active employee count, workforce
  count, pending leave count, new starters this month, department distribution, recent activity,
  and compatibility fields currently used by the frontend-facing contract.
- Leave balance summaries are read-only manual placeholders backed by
  `leave_balance_summaries`. They return `calculation_mode: "manual_placeholder"` and
  `external_integration_enabled: false`; no accrual engine, holiday calendar calculation,
  payroll/bordro, SGK, bank, PDKS, AI, or external integration exists.
- W4C2 locks the current limitation: leave balance reads do not derive balances from leave
  requests. A tenant employee with leave request records but no manual balance summary rows gets
  `200 []`.
- OpenAPI uses readable tags for the public, identity, platform, tenant and organization surfaces.
  Every current tenant-session operation advertises `BearerAuth`, all eight protected platform
  operations advertise only `PlatformBearerAuth`, and public login/selection exchanges remain
  unprotected. The twelve P3K-migrated routes advertise their exact permission plus `401`/`403`
  responses and expose no tenant-selector header parameter.
- Historical W4C6 was a report and smoke-governance refresh only. At that checkpoint the
  implementation report, endpoint draft and smoke agreed on 15 documented endpoints. Historical
  F1A target was 21 generated operations plus runtime `/openapi.json`; historical F1D/F1E have 24
  generated and 25 documented endpoints. F2F has 39 generated and 40 documented endpoints without
  rewriting any earlier checkpoint evidence. The P3K registry had 74 generated operations and 75
  documented runtime endpoints; P4B's three additive profile operations make the current registry
  77 generated operations and 78 documented runtime endpoints.
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
- P0E adds `400 idempotency_key_invalid` for an unusable/repeated key and
  `409 idempotency_key_mismatch` when a tenant-global key is reused with a different semantic
  command. Neither response exposes the stored request fingerprint or response payload.
- For protected employee and leave endpoints, tenant-session authentication and permission checks
  run before service/repository access. Caller tenant headers are ignored, preventing missing,
  malformed or cross-tenant header data from becoming an authority or enumeration oracle.
- FastAPI's generic request validation remains framework default outside the employee and leave
  endpoint scope.
- Local demo seed remains a script command, not an API surface:
  `uv run python scripts/seed_demo_data.py --auth-demo`. It assumes the target local/dev schema
  already exists, idempotently resets the synthetic demo dataset, provisions the canonical admin
  identity in two tenant memberships plus the platform realm, and prints labeled short-lived
  activation URLs for both tenant admin and manager without committing any password/token.
  The command refuses non-local database URL hosts before opening a connection; local hostnames are
  matched case-insensitively.

## Historical baseline: tenant relational integrity and retention

The table below preserves the selected employee/leave relationships recorded at the Phase 0/F2
checkpoint; it is not the complete P3K schema inventory. The current identity, membership, legal
entity, branch, department, position and assignment relationships are documented in
[`01-veritabani-modeli-ve-erd.md`](../05-api-veri/01-veritabani-modeli-ve-erd.md), while populated
backfill and PostgreSQL proof are recorded in
[`13-phase-3-migration-backfill-report.md`](13-phase-3-migration-backfill-report.md).

| Child columns | Parent candidate key | Delete/null behavior |
|---|---|---|
| `leave_requests(tenant_id, employee_id)` | `employees(tenant_id, id)` | `ON DELETE RESTRICT`, required |
| `leave_requests(tenant_id, requested_by_user_id)` | `users(tenant_id, id)` | `NO ACTION`, required |
| `leave_requests(tenant_id, decided_by_user_id)` | `users(tenant_id, id)` | `NO ACTION`, nullable id / `MATCH SIMPLE` |
| `leave_balance_summaries(tenant_id, employee_id)` | `employees(tenant_id, id)` | `ON DELETE RESTRICT`, required |
| `tenant_settings(tenant_id)` | `tenants(id)` root | `ON DELETE CASCADE`, required PK/FK |
| `tenant_feature_flags(tenant_id,key)` | `tenants(id)` root | `ON DELETE CASCADE`, required composite PK + fixed key |

`TENANT_RELATIONSHIP_PREFLIGHT_SQL` also inventories the four root
`tenant_id → tenants.id` links, so orphan ownership rows and the four cross-tenant child links are
reported before constraint DDL. The migration raises a grouped relationship/type/count summary and
does not advance the revision until data is repaired.

PostgreSQL `0009` creates the candidate indexes with `CREATE UNIQUE INDEX CONCURRENTLY`, detects
unexpected name collisions, and replaces a matching invalid leftover index on retry. It then
attaches real unique constraints and adds composite FKs `NOT VALID`; those FKs enforce subsequent
writes immediately while the old scalar FKs coexist. A second preflight runs before the expand
transaction releases its table locks, so a row committed during concurrent index creation cannot
silently enter the expanded revision. `0010` validates all four composite FKs before removing the
legacy constraints. If contract validation nevertheless detects damaged existing data, the database
stays at the safe expanded revision with both constraint generations available for repair.
Alembic uses `transaction_per_migration=True`, so this boundary also holds when an operator invokes
one `upgrade head` command rather than running the two revisions separately.

The SQLite migration branch rebuilds tables only to preserve the fast migration-chain and metadata
checks. P0D enforcement evidence lives exclusively in the `postgres`-marked integration tests.
Existing API/service tenant checks remain defense-in-depth. Historical F1A added principal-scoped
current tenant settings without RLS; F1C now completes the separate PostgreSQL forced-RLS rollout
through revision `0014_f1c_postgresql_rls`.

Revision `0013_tenant_settings` adds the root settings FK after the P0D expand/contract chain, so it
does not alter the historical four-relationship P0D preflight. Its upgrade backfills one fixed
settings row per existing tenant. Its downgrade drops the additive table only when every row still
has defaults; otherwise a `custom_tenant_settings` count aborts before data loss.

Revision `0015_f1d_feature_flags` adds the feature root FK/table and nullable configured active
employee limit after F1C. Existing tenants receive exactly seven frozen defaults. PostgreSQL FORCE
RLS gives app tenant-scoped SELECT and platform SELECT/INSERT/UPDATE only; neither role receives
DELETE. Downgrade refuses feature overrides or configured limits instead of silently discarding
them. Backfill and limit-retention checks transactionally restore tenant-root `ENABLE + FORCE` RLS,
so they do not assume a superuser/BYPASSRLS migration owner; a dedicated PostgreSQL non-bypass
owner test covers backfill, refusal, restoration and clean downgrade.

Revision `0011_p0e_concurrency_idempotency_archive` replaces only the two employee-history delete
actions with `RESTRICT`; it does not weaken their P0D composite tenant keys. Root ownership FKs to
`tenants.id` remain graph-level cascade boundaries so a separately authorized retention/offboarding
procedure can remove an entire tenant graph. No HTTP employee purge route exposes that boundary,
and normal DELETE only sets `employees.archived_at`.

## P0C Command Transaction Boundary

`EmployeeCommandHandler` and `LeaveRequestCommandHandler` pass one tenant-scoped operation to
`SqlAlchemyUnitOfWork.execute`. The UoW requires an idle request session, opens exactly one
transaction, commits on successful operation completion, and rolls back when the service or a later
composed operation fails. Services flush but do not decide durability. Session lifetime remains
owned by the existing FastAPI database dependency.

Read-only routes continue to call their SQLAlchemy-aware services with the request session directly.
No generic repository has been inserted between query code and SQLAlchemy. No audit/outbox schema is
introduced by P0C, but a future recorder can use the same command session before `execute` commits.
The local demo seed remains a separate script command. Its service flushes only, while
`scripts/seed_demo_data.py` owns one `session_factory.begin()` transaction across all tenant/user/
employee/leave seed stages; it is not a migrated API leaf service.

Service rollback regressions inspect flushed employee insert/update/archive and leave
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

The fixture creates a unique temporary database for every PostgreSQL test, runs that migration/API
scenario there, and drops it after the test; it does not downgrade or clear the database named by
the administration URL. Per-test isolation prevents retained archive/idempotency state from making
destructive migration tests collection-order dependent. Runtime engine/sessionmaker creation
belongs to FastAPI lifespan and shutdown disposes the engine. Pool and timeout overrides use these
environment variables:

- `IK_DATABASE_POOL_SIZE`
- `IK_DATABASE_MAX_OVERFLOW`
- `IK_DATABASE_POOL_TIMEOUT_SECONDS`
- `IK_DATABASE_POOL_RECYCLE_SECONDS`
- `IK_DATABASE_CONNECT_TIMEOUT_SECONDS`
- `IK_DATABASE_STATEMENT_TIMEOUT_MS`
- `IK_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS`

At the historical P0A checkpoint, this foundation changed database wiring and test evidence only;
the then-current API/OpenAPI operation set and tenant-header compatibility were unchanged because
auth, RBAC, RLS and new product features were outside P0A. P3K's active behavior is documented at
the top of this report and no longer authorizes dashboard/employee/leave routes by tenant header.

## Smoke Coverage

The default `uv run python scripts/backend_api_smoke.py` invocation runs locally through ASGI and
SQLite. The PostgreSQL baseline invokes the same script with `--database-url` against its disposable
test database. Neither path uses deploy, staging URLs, cron, tokens, credentials, `.env`, or external
services.

Current P4B documentation expects the registry to contain 78 rows: 77 generated operations plus
runtime `/openapi.json`. Smoke executes every row, using real credentials for browser-facing
tenant/platform auth and narrowly scoped dependency overrides only for historical trusted-principal
compatibility paths. It verifies activation, email-only login, one- and multi-org selection,
refresh/logout, realm token cross-use denial, tenant-admin user/role/audit behavior, organization
administration, assignment/team/chart flows, Employee 360 read/personal/employment mutations,
independent stale-version conflict handling, cross-tenant hiding, employee mutation denial,
tenant-header spoof resistance, projected no-HR platform output, exact security metadata and
bounded cursors.
Historical Phase-0/F1A/F1B smoke evidence below remains checkpoint evidence only.

The script now verifies the documented API surface in four directions:

- Every generated OpenAPI operation must be listed in the smoke registry, and every OpenAPI
  operation in the registry must exist in the generated schema.
- The `Completed API Surface` table in this report must match the smoke registry, including the
  runtime `/openapi.json` endpoint.
- The `Güncel uygulama yüzeyi` table in `03-openapi-endpoint-taslagi.md` must match the same smoke
  registry.
- Every endpoint in the smoke registry must be executed by at least one runtime smoke scenario,
  including `/openapi.json` and each tenant-scoped domain path.

The historical Phase-0 runtime scenarios verify:

- `/health`, `/`, and `/openapi.json`.
- Tenant header missing, invalid, repeated, and cross-tenant behavior.
- Employee create/idempotent replay/list/detail/update/archive/repeated archive, filters,
  cursor plus offset-compatibility pagination, lifecycle status handling, error envelopes,
  history-preserving visibility, and tenant isolation.
- Leave balance read-only summaries, `period_year` filtering, placeholder flags, tenant
  isolation, and the absence of synthetic balances from leave request records.
- Leave request create/list/approve/reject/cancel, keyed decision replay, filters, mixed-order
  cursor plus offset-compatibility pagination, transition conflicts, error envelopes,
  cross-tenant user/request checks, date-window behavior, and tenant isolation.
- Dashboard counts, department distribution, recent activity shape, and tenant isolation.

The F1A runtime and focused contract scenarios verify provisioning/list/detail/lifecycle PATCH,
current tenant/settings GET/PATCH, typed extra-key rejection, region immutability,
suspended/offboarding/closed behavior, cross-tenant principal isolation, and the absence of
employee/leave data from platform output.

F1B scenarios additionally verify frozen/slotted and derived request contexts, safe error/log
allowlists, canonical/malformed/duplicate/conflicting correlation inputs, worker serialization,
seven Phase-1 envelopes, cursor-only platform pagination, and unchanged Phase-0 employee/leave
plain-array contracts.

F1D API/event tests additionally verify three feature operations, exact seven-key ordering and
defaults, default/override source transitions, strict/unknown/duplicate input rejection, tenant A/B
isolation, tenant-principal denial across every platform tenant operation, configured limit
propagation without HR count, terminal lifecycle hardening, four redacted event shapes and no event
on no-op/failure. The synchronized script/registry provides the final 25-endpoint F1D smoke evidence;
the full required command results are recorded below.

F2F scenarios additionally verify all 15 additive operations, invite/activation and secure-session
lifecycle, tenant-admin user/role/audit happy paths, employee permission denial, cross-tenant
not-found behavior, platform/tenant audit separation and safe audit projections. Playwright covers
the same product-visible journeys with same-origin API interception so the browser gate remains
deterministic; PostgreSQL integration separately proves storage/RLS/grant/immutability claims.

P3K scenarios additionally verify that the twelve historical dashboard/employee/leave operations
cannot be authorized by tenant headers, a platform token, or a tenant role missing their exact
permission. They also execute both organization memberships, the separate platform realm, all
organization write/read surfaces, derived manager scope and lazy chart expansion. PostgreSQL tests
remain the authority for RLS/grants, populated migration backfill, department cycle/concurrency and
bounded-query/index claims.

## Historical checkpoint verification evidence

### Historical F2F Phase 2 hardening gates

| Gate | Command | Current evidence state |
|---|---|---|
| Backend Ruff | `uv run ruff check backend` | Passed: `All checks passed!` |
| Full fast backend suite | `uv run pytest` | Passed: 787 passed, 41 PostgreSQL tests deselected, 1 known Starlette/httpx deprecation warning |
| Role × scope × endpoint matrix | `uv run pytest -q backend/tests/test_audit_api.py backend/tests/test_authorization_api.py` | Passed: 6 tests; all seven tenant roles, three audit categories, hidden `404` vs denied `403`, cross-tenant and platform boundaries, signed super-admin bearer negative |
| OpenAPI/current contract | `uv run pytest -q backend/tests/test_openapi_contract.py backend/tests/test_openapi_metadata.py` | Passed: 27 tests; 24 exact historical operations + 15 additive F2 operations, exact ten-operation `BearerAuth` set, no duplicate current snapshot |
| Migration fast lane | `uv run pytest -q backend/tests/test_migrations.py` | Passed: 38 tests; linear sole-head chain, SQLite compatibility, offline DDL and downgrade guards |
| Alembic head | `uv run alembic heads` | Passed: sole head `0021_f2f_user_insert_grant` |
| Backend executable smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 40 documented runtime endpoints executed and docs/OpenAPI registry exact |
| Full PostgreSQL 17.10 lane | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed: 41 tests; migration round-trip/drift, runtime RLS/grants, auth/session/RBAC/audit, concurrency and migrated API smoke |
| Focused F2 PostgreSQL security | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_f2[a-e]_*.py` | Passed: 9 tests; activation/session isolation, user search, role assignment/versioning, append-only audit and tenant/platform separation |
| Bounded-query smoke | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_f2f_query_smoke.py -s` | Passed: 1 test over 1,000 users/events; login 4 SELECT + 4 INSERT + 5 SET, user list 2 SELECT + 2 SET, audit list 1 SELECT + 2 SET |
| Frontend static gates | `npm run lint && npm run typecheck && npm run build` in `frontend/` | Passed; production build includes `/activate`, `/login`, `/dashboard`, `/users`, `/audit`, `/platform`, `/platform/audit` |
| Focused browser E2E | `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/opt/data/pw-browsers/chromium-1223/chrome-linux/chrome npm run test:e2e` | Passed: 7 Chromium tests; connected invite → activate → login → refresh → logout, admin user/role flow, employee denial, tenant audit and platform-shell separation |
| Git hygiene | `git diff --check` plus task-scope review | Passed; no deployment, staging, cron, credential, `.env` or Phase 3 change |

At the historical F2F checkpoint, the queue stopped before Phase 3 and the supervisor owned the
review-branch push. The active stop/review decision is now the P3K gate at the top of this report.

### Historical F1E Phase 1 closure gates — local technical gates passed; supervisor push pending

| Gate | Command | Current evidence state |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed, `All checks passed!` |
| Fast suite | `uv run pytest -q` | Passed: 759 passed, 30 deselected, 1 warning |
| OpenAPI contract/security metadata | `uv run pytest -q backend/tests/test_openapi_metadata.py backend/tests/test_openapi_contract.py` | Passed: 26 tests, 1 warning; exact F1E snapshot and F1D-to-F1E principal-metadata-only diff |
| Focused Phase 1 security | `uv run pytest -q backend/tests/test_tenant_api_f1a.py backend/tests/test_tenant_api_f1d.py backend/tests/test_platform_tenant_queries.py backend/tests/test_tenancy.py backend/tests/test_worker_queue.py backend/tests/test_request_context.py backend/tests/test_correlation_middleware.py backend/tests/test_platform_events.py` | Passed: 244 tests; all ten operation denials, A/B API/cache/explicit-origin worker boundaries, fake lookalike rejection, no-HR platform fields and redacted correlation/event fixtures |
| Service-layer tenant isolation | `uv run pytest -q backend/tests/test_employee_service.py backend/tests/test_leave_request_service.py` | Passed: 44 tests; employee/leave list, get, mutation and relationship guards remain tenant-scoped without relying on API routing |
| Migration suite | `uv run pytest -q backend/tests/test_migrations.py` | Passed: 36 tests; upgrade/downgrade guards, offline security DDL and portable drift/round-trip coverage |
| Alembic head | `uv run alembic heads` | Passed: sole head `0015_f1d_feature_flags` |
| PostgreSQL full lane | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed on PostgreSQL 17.10: 30 passed, 759 deselected, 1 warning |
| PostgreSQL migration/runtime baseline | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_baseline.py` | Passed: 8 tests; real `base → head → base → head`, downgrade refusal, native catalog, zero autogenerate drift and migrated API smoke |
| PostgreSQL RLS/direct-DB attacks | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_f1c_rls.py backend/tests/integration/test_postgresql_tenant_relational_integrity.py` | Passed: 12 tests; catalog/FORCE/role checks, raw A/B denial, repository and pool binding, platform-HR denial and every composite relationship negative |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`; all 25 documented endpoints executed and Phase 1 principal metadata checked |
| Git hygiene | Exact commands below from `54a3678`; final `git status --short --branch` and upstream count in handoff | Passed: no whitespace, forbidden path or credential-pattern match across the F1E files; only task-scoped code/test/docs changes. Final clean/ahead state is verified after the F1E HEAD commit in the handoff. |

The F1E hygiene audit is reproducible after the checkpoint commit with:

```bash
git diff --check 54a3678...HEAD
test -z "$(git diff --name-only 54a3678...HEAD | \
  rg -i '(^|/)(\.env($|\.)|.*secret.*|.*credential.*|.*token.*|.*staging.*|.*cron.*|.*deploy.*|.*auth.*)')"
test -z "$(git diff --format= --unified=0 54a3678...HEAD | \
  rg -i '^\+[^+].*(api[_-]?key|client[_-]?secret|access[_-]?token|private[_-]?key|password)\s*[:=]\s*[^[:space:]]+')"
git status --short --branch
git rev-list --left-right --count '@{upstream}...HEAD'
```

The F1A-F1D implementation base was already pushed on the review branch before this closure block.
Per task authority, F1E HEAD is intentionally not pushed by Codex; the supervisor owns that push.
At that historical checkpoint, the queue remained at
`STOP — supervisor F1E push pending; awaiting Murat review`, and Phase 2 authentication, session,
RBAC, permission enforcement and audit persistence had not started yet.

### F1D required gates — passed

| Gate | Command | Current evidence state |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed |
| Fast suite | `uv run pytest -q` | Passed: 741 passed, 30 deselected; one known Starlette/httpx deprecation warning |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed: `BACKEND_SMOKE_OK`, 25/25 documented endpoint coverage |
| OpenAPI contract | `uv run pytest -q backend/tests/test_openapi_metadata.py backend/tests/test_openapi_contract.py` | Passed; exact 24-operation F1D snapshot and historical subset/diff assertions |
| SQLite migration/API/event focus | `uv run pytest -q backend/tests/test_migrations.py backend/tests/test_tenant_api_f1d.py backend/tests/test_platform_events.py` | Passed in focused and full suites; SQLite remains compatibility evidence only |
| PostgreSQL full lane | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed on PostgreSQL 17.10: 30 passed, 735 deselected; one known deprecation warning |
| PostgreSQL F1D security | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed current-head catalog, A/B flag RLS, exact/no-DELETE ACLs, platform-HR denial, non-BYPASS owner backfill/refusal/restoration and migrated API smoke |

The continuation adds six fast authorization/event proof cases and documentation corrections only;
runtime, migration and PostgreSQL test code remain identical to the recorded 30-test PostgreSQL
17.10 lane. A PostgreSQL admin DSN was not available for a fresh continuation rerun.

The F1D commit SHA is reported through Git history and the final handoff rather than embedded as
self-referential document content. The historical passed
sections below remain evidence for their own F1A/F1B/F1C checkpoints only.

### F1C required gates — passed

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed, `All checks passed!` |
| Fast SQLite | `uv run pytest -q` | Passed, 609 tests; 28 PostgreSQL tests deselected; one known Starlette warning |
| PostgreSQL 16.4 | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed, 28 tests; 609 fast tests deselected; fresh disposable database per test |
| F1C PostgreSQL security | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_f1c_rls.py` | Passed, 6 tests; catalog, roles, raw SQL, HTTP binding, platform denial, pool reset, UoW and repository proof |
| Migration round-trip | PostgreSQL baseline + `uv run pytest -q backend/tests/test_migrations.py` | Passed, real `base → head → base → head` and 30 fast migration tests |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed, `BACKEND_SMOKE_OK`; all 22 documented endpoints executed |
| PostgreSQL API smoke | Baseline `test_full_api_smoke_uses_alembic_migrated_postgresql` | Passed against Alembic head with runtime app/platform role binding |

The PostgreSQL lane used a local user-space PostgreSQL 16.4 server only to create disposable test
databases. No staging/production database, deployment, credential file, auth file, `.env`, secret,
push, merge or deploy was changed. Endpoint and generated OpenAPI operation counts remain unchanged.

### F1B required gates — passed

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed, `All checks passed!` |
| Fast suite | `uv run pytest -q` | Passed, 598 tests; 22 PostgreSQL tests deselected; one known Starlette warning |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed, `BACKEND_SMOKE_OK`; all 22 documented endpoints plus correlation, envelope, cursor and compatibility checks |

F1B adds no database schema or migration and makes no new PostgreSQL-specific catalog/index claim.
The existing opt-in PostgreSQL baseline continues to invoke this same expanded smoke against an
Alembic-migrated disposable database when that lane is run.

### F1A required gates — passed

| Gate | Command | Result |
|---|---|---|
| Ruff | `uv run ruff check backend` | Passed, `All checks passed!` |
| Fast SQLite | `uv run pytest -q` | Passed, 552 tests; 22 PostgreSQL tests deselected; one known Starlette warning |
| PostgreSQL 17.10 | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` | Passed, 22 tests; 552 fast tests deselected; includes 7 migration/runtime/settings baseline tests and 3 F1A transaction/concurrency tests |
| Backend smoke | `uv run python scripts/backend_api_smoke.py` | Passed, `BACKEND_SMOKE_OK`; all 22 documented endpoints executed |
| OpenAPI contract | `uv run pytest -q backend/tests/test_openapi_metadata.py backend/tests/test_openapi_contract.py` | Passed, 16 tests; 21 generated operations, exact F1A snapshot and unchanged Phase-0 operation/components |
| SQLite migrations | `uv run pytest -q backend/tests/test_migrations.py` | Passed, 26 tests; backfill, round-trip, drift and custom-settings downgrade refusal |
| PostgreSQL F1A baseline | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_baseline.py` | Passed, 7 tests; native constraints/FK, backfill/round-trip/refusal, drift, runtime and API smoke |
| PostgreSQL F1A concurrency | `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres backend/tests/integration/test_postgresql_f1a_tenant_concurrency.py` | Passed, 3 tests; same-slug create winner, lifecycle row-lock serialization and typed-settings partial-update serialization |

The PostgreSQL lane used a disposable local PostgreSQL 17.10 cluster and a fresh database per test.
No staging/production database, deployment, credential file or `.env` was changed.

### Historical Phase-0 verification evidence

This is retained P0F evidence for the former employee-number cursor. It does not claim PostgreSQL
execution of the P4A immutable-cursor repair.

P0F local gate evidence:

- `uv run ruff check backend`: passed.
- `uv run pytest -q`: passed, 420 fast tests passed and 17 PostgreSQL tests deselected; the one
  existing Starlette `TestClient` deprecation warning remains.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, all 15 documented
  endpoints covered, including employee/leave cursor traversal, no-overlap and cursor/offset
  conflict checks.
- PostgreSQL 16.4 user-space test cluster with
  `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres`: passed, 17 integration tests passed and
  420 fast tests deselected. This includes Alembic round-trip/drift plus the disposable 10,000
  employee/5,000 leave `EXPLAIN (ANALYZE, BUFFERS)` regression.
- Captured selective search used both employee trigram GIN indexes; employee and leave deep pages
  used `uq_employees_tenant_employee_number` and
  `ix_leave_requests_tenant_created_cursor`. Dashboard query-count tests enforce 4 default/2
  without activity versus the pre-P0F 7/5 baseline.

Required P0F completion gates are the four commands above. Timing/buffer evidence and the exact
repeat procedure are in `12-phase-0-query-performance-baseline.md`; elapsed time is evidence rather
than a hardware-sensitive pass/fail assertion.

P0E regression coverage includes:

- fast database-backed command tests for semantic replay, changed payload/command mismatch,
  tenant-global key isolation, keyed leave create/decision replay, and failed-command receipt
  rollback;
- employee API/service/dashboard/leave/balance regressions proving archive visibility,
  idempotent repeated `204`, employee-number reservation, preserved history, and tenant isolation;
- migration/model parity for `archived_at`, `command_idempotency`, its named tenant-key unique
  constraint, and both employee child `RESTRICT` relationships;
- real PostgreSQL tests proving one terminal approve/reject winner, one resource/receipt for a
  concurrent same-key leave create, preserved leave/balance history after archive, and named FK
  rejection of a direct employee deletion;
- updated OpenAPI metadata and local smoke coverage for optional idempotency and archive semantics.

Required P0E completion gates are:

- `uv run ruff check backend`
- `uv run pytest -q`
- `uv run python scripts/backend_api_smoke.py`
- `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` for PostgreSQL row-lock, concurrent
  claim, and retention-FK evidence.

P0E local gate evidence:

- `uv run ruff check backend`: passed.
- `uv run pytest -q`: passed, 407 fast tests passed and 16 PostgreSQL tests deselected; the one
  existing Starlette `TestClient` deprecation warning remains.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, all 15 documented
  endpoints covered, including create/decision replay and repeated employee archive scenarios.
- PostgreSQL 16.4 user-space test cluster with
  `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres`: passed, 16 integration tests passed and
  407 fast tests deselected. This includes synchronized duplicate-create, leave-decision,
  same-key claim, archive/history retention, direct-delete rejection, migration/drift, tenant
  integrity, runtime, and PostgreSQL-backed API smoke coverage.

P0D regression coverage includes:

- model metadata and migrated-schema parity for both parent candidate keys and all four composite
  foreign keys;
- PostgreSQL preflight detection of both cross-tenant and deliberately injected orphan rows before
  expansion;
- exact PostgreSQL constraint definitions, validation state, and named direct-write rejection for
  each tenant-owned relationship;
- valid-data `0008 → head → 0008 → head` preservation, including legacy constraint restoration;
- existing API, tenant-isolation, OpenAPI operation, migration, and smoke regressions.

Required P0D completion gates are:

- `uv run ruff check backend`
- `uv run pytest -q`
- `uv run python scripts/backend_api_smoke.py`
- `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` for the PostgreSQL-specific acceptance
  evidence.

P0D local gate evidence:

- `uv run ruff check backend`: passed.
- `uv run pytest -q`: passed, 390 fast tests passed and 12 PostgreSQL tests deselected; the one
  existing Starlette `TestClient` deprecation warning remains.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, all 15 documented
  endpoints covered.
- PostgreSQL 16.4 user-space test cluster with
  `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres`: passed, 12 integration tests passed and
  390 fast tests deselected. This includes five P0D-specific PostgreSQL tests plus the existing
  migration/drift/API/runtime and command-transaction probes.
- Generated `alembic upgrade head --sql` was also applied successfully to an empty disposable
  PostgreSQL 16.4 database, including the online-equivalent preflight blocks, concurrent candidate
  indexes, `NOT VALID` FKs, per-revision commits, validation, and contract removal.

Historical P0C regression coverage includes:

- service-level no-commit/flush assertions for employee and leave migrated writes;
- forced post-flush rollback with fresh-session persistence checks;
- successful command persistence through the single UoW transaction owner;
- centralized compatibility mapping for existing domain errors, the named employee duplicate
  constraint, unknown integrity conflicts, and stale/recognized concurrent writes;
- existing API, tenant-isolation, OpenAPI operation, migration, and smoke regressions.

Required P0C completion gates were:

- `uv run ruff check backend`
- `uv run pytest -q`
- `uv run python scripts/backend_api_smoke.py`

Historical P0C local gate evidence:

- `uv run ruff check backend`: passed.
- `uv run pytest -q`: passed, 385 fast tests passed and 7 PostgreSQL tests deselected; the one
  existing Starlette `TestClient` deprecation warning remains.
- `uv run python scripts/backend_api_smoke.py`: passed, `BACKEND_SMOKE_OK`, all 15 documented
  endpoints covered.
- The two new PostgreSQL command-transaction probes cover a synchronized employee unique race and
  real `55P03` lock-conflict mapping. They were collected but could not be executed locally because
  this worktree has neither a running Docker daemon nor an `IK_TEST_DATABASE_URL` admin DSN; the
  configured PostgreSQL lane remains the required runtime evidence for those PostgreSQL-specific
  claims. This sentence describes the historical P0C checkpoint; P0G has now executed both probes
  successfully inside the 17-test PostgreSQL 16.4 lane.

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

## Post-P4B backlog — outside this task

P4B closes only the approved focused Employee 360 slice. It does not authorize P4C or any later
product module.

- Enforced privileged-role MFA/step-up remains deferred. Separate platform login, audience,
  cookie, live session/principal, tenant administration and platform audit demo are implemented;
  future step-up must strengthen that realm without converting a platform session into a tenant
  session.
- The historical `/api/v1/tenant` metadata/settings/feature compatibility surface still uses its
  explicit trusted tenant-principal adapter. Browser-facing identity, organization and migrated HR
  routes use live sessions; any later migration of this compatibility seam requires its own
  approved contract slice.
- Global sort controls and validation/error normalization beyond the endpoint families already
  covered. Immutable `RequestContext`, global correlation middleware and the new Phase-1
  `{data,meta}` standard are implemented; remaining Phase-0 envelope migrations require an explicit
  version/deprecation decision.
- Idempotency receipt TTL/cleanup policy and expansion beyond the current employee-create and
  leave-create/decision command scope.
- Authorized retention/offboarding orchestration around the tenant-root graph boundary; there is
  intentionally no employee purge HTTP endpoint.
- Optional leave request detail endpoint if product workflow needs direct request reads.
- Leave policy/accrual calculation, holiday calendars, manual adjustments/imports, and employee
  self-service leave balance views.
- Employee documents, broader field security, import/export, lifecycle workflow, reporting,
  analytics, notification/mail and all other P4C+ endpoints remain later MVP phases. P4B is not
  approval for sensitive identity/financial/health fields or assignment ownership duplication.
- Activating the documented CI template remains repository administration outside this block; the
  template now describes both the fast SQLite and PostgreSQL service-backed test steps.
