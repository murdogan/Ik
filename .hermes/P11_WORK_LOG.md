# Phase 11 Work Log

Status: in progress
Started: 2026-07-27T13:03:41Z
Starting plan SHA: `37150c8e8a8afb6459a74a2dfbf5166431ec3353`
Branch: `codex/mvp-phase11-final-validation`
Authoring: Codex `gpt-5.6-sol` with `ultra` reasoning; Hermes supervises
staging acceptance and merge.

Credentials, tokens, DSNs, and personal data are never recorded here. The
disposable PostgreSQL 17 administrator DSN is represented as `[REDACTED]`.

## Gate ledger

| Block | State | Evidence | Defects repaired |
|---|---|---|---|
| P11A inventory/baseline | complete | 100 backend test files; 1,128 initial cases (1,056 default + 72 PostgreSQL); 42 initial migrations through `0042`; 142 API paths / 177 operations / 381 schemas; 36 frontend routes; 36 initial Chromium cases | Two collection blockers repaired |
| P11B backend regression | repair in progress | Initial full default lane: 284 failed, 766 passed, 72 deselected, 6 errors; repaired focused backend lanes are green and OpenAPI/smoke confirmation is in progress | Authorization catalog serialization, dashboard UTC projection, current lifecycle/profile fixtures/contracts, migration compatibility harness, leave lineage/date validation, and architecture boundaries |
| P11C PostgreSQL/RLS | repair in progress | PostgreSQL 17.10 baseline: 61 passed / 11 failed; all reproduced fixture failures are repaired and focused nodes are green; one real lifecycle ACL defect has a least-privilege forward-migration repair under focused confirmation | Current P6 SQL fixtures, privacy model default drift, guarded downgrade remediation, session-policy selection, tenant FK fixtures, archive/profile locking, and performance data |
| P11D frontend/E2E | focused repairs green | Clean install/typecheck/lint/build green; baseline Chromium 22 passed / 14 failed; every original failure and 16 added Phase 11 cases has a latest focused pass | Strict feature fixtures, current Employee 360 contracts, authorization selectors, 17 previously untouched routes, and PWA cache isolation |
| P11E security/performance | in progress | Production dependency and verified secret scans green; 10k PostgreSQL query-plan proof, document/object boundary, and full synthetic PostgreSQL backup/restore/rollback proof green | Current performance fixtures, PWA authenticated-data cache proof, and real PostgreSQL recovery evidence |
| P11F final/report | pending | Final complete gate is intentionally reserved until focused repairs are green | pending |

## P11A — inventory and one-time baselines

### Collection and inventory

- `uv run pytest --collect-only -q`
  - Initial collection failed in two modules: repository root was absent from
    pytest's Python path for `scripts`, and the historical PostgreSQL
    performance test imported a dashboard statement that had been inlined.
  - After repair: `1056/1128 tests collected (72 deselected) in 12.34s`.
- `IK_TEST_ADMIN_DATABASE_URL=[REDACTED] uv run pytest --collect-only -q -m postgres`
  - `72/1128 tests collected (1056 deselected) in 12.25s`.
- `npx playwright test --list`
  - 36 configured Chromium cases across 15 files before P11 coverage repair.
- Runtime inventory from `create_app().openapi()`:
  - 142 paths, 177 operations: GET 84, POST 67, PATCH 21, DELETE 4, PUT 1.
  - 381 component schemas.
- Frontend inventory: 36 application routes.
- Alembic inventory: 42 revision files; one linear head,
  `0042_p9_privacy_evidence_hardening`.

Collection repairs:

1. Added the repository root to pytest `pythonpath` so the tracked recovery CLI
   tests can import `scripts` without environment-specific path mutation.
2. Restored `_dashboard_counts_statement` as the bounded query builder used by
   both runtime dashboard aggregation and the historical PostgreSQL plan gate.

### Backend baseline

- `uv run ruff check backend scripts`
  - Passed.
- `uv run ruff format --check backend scripts`
  - Baseline failed: 145 files would reformat; 248 already formatted.
- `uv run pytest -q`
  - `284 failed, 766 passed, 72 deselected, 31 warnings, 6 errors in 961.01s`.
  - Failures were classified before repair; the largest groups were stale
    tenant/leave fixtures and contracts, the SQLite migration compatibility
    harness, dashboard authorization fixtures, employee lifecycle/profile
    contracts, and OpenAPI registries.

### Frontend baseline

- `npm ci`
  - Passed; 352 packages installed.
- `npm audit --omit=dev --audit-level=high`
  - Passed; 0 production vulnerabilities.
- `npm run typecheck`
  - Passed.
- `npm run lint`
  - Passed.
- `npm run build`
  - Passed with Next.js 16.2.12; 34 static pages generated.
- `npx playwright test`
  - `22 passed, 14 failed in 5.0m`.
  - Failures were retained as the single broad browser baseline and assigned to
    focused fixture/current-contract repair. The final complete Chromium run
    has not yet been consumed.

## P11B — demonstrated repairs and focused evidence

### High — authorization catalog field target caused a 500

`GET /api/v1/permissions` coerced field-policy target `work_email` into the
scope-only `PermissionRead.scope` literal. The response validator raised and
returned 500.

Repair:

- Catalog records now distinguish `target_type` (`scope` or `field`).
- Field targets are exposed in `target`; only scope targets populate `scope`.
- Backend schema/API, frontend contract, and authorization regression were
  updated together.

Evidence:

- `uv run pytest -q backend/tests/test_authorization_api.py
  backend/tests/test_audit_security_matrix.py`
  - 4 passed.

### P2 — dashboard activity rejected SQLite timestamps

SQLite returns persisted `AuditEvent.occurred_at` values without timezone
metadata. `DashboardActivityItem` requires an aware timestamp, causing every
non-empty recent-activity projection to fail validation. The dashboard service
now normalizes database timestamps to UTC at its projection boundary.

Focused dashboard result is pending the concurrent fixture lane's final rerun.

### P2 — module architecture gate had 76 violations

Document runtime/scanning, notification email, and reporting spreadsheet
adapters added in later phases lived directly at module package roots and
crossed the repository's explicit layering boundary.

Repair:

- Document runtime/scanning moved under the document infrastructure layer and
  now uses a structural settings contract rather than importing legacy config.
- Notification email contracts moved to the notification application layer;
  the legacy SQLAlchemy capture adapter remains in the legacy service boundary.
- Reporting import constants moved to an application contract and spreadsheet
  handling moved to reporting infrastructure.
- Call sites now import explicit layer paths; module package roots are markers.

Evidence:

- `uv run pytest -q backend/tests/test_import_boundaries.py`
  - 28 passed.
- A post-repair default collection completed with 1,055 default cases and 72
  PostgreSQL cases; one invalid duplicate SQLite current-head migration claim
  was removed by the migration harness repair.

### Employee lifecycle/profile current-contract repair

The old suite still created terminated employees directly, changed lifecycle
fields with generic PATCH, and archived active employees without mandatory
profile rows. Current production deliberately requires versioned explicit
lifecycle transitions, terminal termination, complete Employee 360 persistence,
and archive-after-termination.

Repair:

- Fixtures now create the mandatory personal/employment profile aggregate.
- Tests exercise explicit lifecycle transition and archive endpoints, same-day
  termination, terminal-state rejection, tenant-scoped archive, and idempotent
  archive.
- Employee 360 exact contracts now include archive/end-date/termination fields.

Evidence:

- Four employee API/schema/service/transaction files: 153 passed / 1 stale-ID
  assertion failed in 105.08s.
- Corrected stale-ID node: 1 passed in 3.05s.
- Manager/field-policy/profile/correlation focused lane after repair:
  28 passed / 1 stale registry entry failed; the registry entry was then
  corrected and awaits its focused confirmation.

### Tenant/leave/migration fixture and harness repair

- Tenant F1A: 66 passed in 92.70s.
- Tenant F1D: 50 passed in 81.48s.
- Leave service and command-idempotency focused lanes: 26 passed and 6 passed.
- Migration baseline: 46 passed / 23 failed in 177.02s.
- Migration repair preserves immutable revisions, freezes supplementary SQLite
  compatibility at revision `0035`, and leaves current-head/drift ownership to
  real PostgreSQL.
- Migration focused final: 68 passed in 170.49s; Ruff and diff checks passed.

### Harness-only corrections

- The staging refresh-cookie unit test now constructs the current protected
  runtime contract directly instead of starting an application that correctly
  requires unavailable S3/ClamAV services. Exact secure host-only cookie
  policies remain asserted.
- Current default feature catalog expectations now include the deployed
  self-service and notification modules.

### Leave/demo-seed focused final evidence

- `uv run pytest -q backend/tests/test_command_idempotency.py
  backend/tests/test_dashboard.py backend/tests/test_leave_balance_api.py
  backend/tests/test_leave_request_api.py backend/tests/test_leave_request_service.py
  backend/tests/test_demo_seed_service.py backend/tests/test_demo_seed_command.py`
  - 114 passed, 1 dependency deprecation warning, in 126.61s.
- Full leave-request API file: 46 passed in 55.37s.
- Dashboard plus leave-balance files: 25 passed with 1 warning in 59.51s.

Demonstrated product fixes:

1. Legacy-compatible leave writes now resolve and store the current P6 leave
   type/policy lineage and coherent decision timestamps.
2. Demo seed now provisions deterministic P6 configuration, calendar, counted
   days, timeline, and ledger facts idempotently.
3. P6 request creation refreshes its server-populated parent timestamp before
   child fact creation, preventing the demonstrated async `MissingGreenlet` 500.
4. Every leave input date, including query filters, uses the strict `DateOnly`
   contract and rejects datetime/numeric coercion.

### OpenAPI and backend runtime smoke

- OpenAPI/metadata baseline: 13 failed / 18 passed.
- `uv run pytest -q backend/tests/test_openapi_metadata.py
  backend/tests/test_openapi_contract.py`
  - 31 passed, 1 warning, in 65.34s after repair.
- `uv run python scripts/backend_api_smoke.py`
  - exited 0 with `BACKEND_SMOKE_OK`;
  - executed 80 documented endpoint checks and validated the exact 177-operation
    Phase 11 registry.

Repair:

- Replaced the stale 77-operation checkpoint assumption with an exact sorted
  current registry while retaining every historical snapshot compatibility
  assertion.
- Reconciled `{request_id}` leave paths and current lifecycle/balance contracts.
- Filled missing authentication, authorization, validation, not-found,
  conflict, idempotency, pagination, and safe-correlation metadata on current
  leave operations.

## P11C — disposable PostgreSQL 17 evidence

The only database used is the disposable PostgreSQL 17.10 cluster under an
explicit `/opt/data/tmp/ik-p11-*` root. Its administrator DSN remains
`[REDACTED]`.

### One-time complete baseline

- `IK_TEST_DATABASE_URL=[REDACTED] uv run pytest -q -m postgres`
  - 61 passed, 11 failed, 1,055 deselected, 11 warnings in 378.38s.

The failures separated into current-schema fixture drift plus two demonstrated
product defects: privacy model/server-default drift and a lifecycle profile-row
lock that PostgreSQL denied after the intentional P4E raw-update revocation.

### Focused repaired PostgreSQL evidence

- Three concurrency/archive nodes:
  - 3 passed in 11.59s.
  - Current P6 type/policy fixtures replaced obsolete raw leave rows.
  - Current archive fixtures include the mandatory Employee 360 aggregate and
    terminate before archive.
  - Tenant deletion is correctly rejected when it would erase append-only P6
    facts; the old cascade expectation was removed.
- Session RLS plus two relational-integrity nodes:
  - 3 passed in 14.82s.
  - The session catalog assertion now selects the tenant isolation policy rather
    than collapsing multiple valid policies by table.
  - Revision-aware SQL creates valid leave lineage/decision state before
    exercising composite cross-tenant foreign keys.
- Representative 10k plan node:
  - 1 passed in 6.37s.
  - 10,000 tenant employees and 5,000 current-contract leave rows.
  - Employee search selected employee-number/email/full-name trigram indexes.
  - Employee and leave cursor queries selected their intended partial/keyset
    indexes, returned 51 rows, and removed 0 and 1 row respectively.
  - Dashboard aggregate returned one row. Measured execution times are evidence
    only, not an invented production SLO.

### High — PostgreSQL lifecycle/profile lock authorization

P4E intentionally revoked raw tenant-role `UPDATE` on personal profiles, but
PostgreSQL also requires that privilege for `SELECT ... FOR UPDATE`. Current
lifecycle and personal-profile writes tried that direct row lock and returned a
500 despite valid application authorization.

Repair:

- Added the forward-only
  `0043_p11_employee_lifecycle_profile_lock` migration; the repository now has
  43 revisions and that revision is the single head.
- Its fixed-query `SECURITY DEFINER` gateway validates the login capability,
  transaction-local tenant/actor/membership, active eligible membership, exact
  `employee:update:tenant` permission, and same-tenant employee before taking
  the lock.
- Function owner/search path/EXECUTE ACL are fixed and audited. Tenant table and
  column `UPDATE` remain denied; platform/authentication roles cannot execute
  the gateway.
- Missing actor/membership and cross-tenant IDs return false. Authorized
  same-tenant calls return true.
- No historical migration was edited.

Evidence:

- Four original PostgreSQL baseline nodes: 4 passed with 10 expected
  computed-default warnings in 28.39s.
- Final gateway catalog plus real-PostgreSQL API smoke nodes: 2 passed in
  19.22s.
- Affected employee/profile/migration default files: 99 passed in 137.72s.
- Privacy consent-purpose `created_at` now matches the `now()` server default in
  migration `0041`, eliminating the demonstrated exact model drift.

### High — archive/profile-submission transaction race

The first archive privilege workaround locked the employee first and read
profile sections without locks. A deterministic PostgreSQL proof showed the
P4E submit command could validate an active employee, wait behind archive, and
then return `submitted` after `archived_at` committed. That left a submitted
profile-change request for a read-only archived employee.

Repair:

- Restored the canonical personal-profile gateway → employment-profile →
  employee → blocker-check order used by profile writers.
- Revision `0043` now adds a shared transaction advisory fence and a
  fail-closed `BEFORE INSERT` active-employee guard. Both archive/lifecycle and
  P4E insert paths serialize on the same employee key; the guard rechecks the
  exact tenant/employee after the fence and suppresses the insert if the
  employee is missing or archived.
- The guard uses only the private executor's existing read privilege. Raw
  tenant table/column `UPDATE` remains denied.

Evidence:

- Pre-fix deterministic real-PostgreSQL proof: 1 failed in 3.92s because
  submission incorrectly returned `submitted` after archive committed.
- Post-fix canonical real-service regression: 1 passed in 4.10s; archive won,
  submission returned a safe conflict, and zero request/audit rows remained.
- Compact affected PostgreSQL set: 3 passed in 8.54s.
- Affected default archive/lifecycle service/API/transaction set: 7 passed in
  8.23s.

### P2 — non-super migration-owner portability

Revision `0043` initially transferred its security-definer function to the
private executor while that role intentionally lacked `CREATE` on `public`.
PostgreSQL requires that capability for `ALTER FUNCTION ... OWNER`; the
superuser administrator lane masked the failure.

Repair and evidence:

- Added the established private-owner safety preflight.
- The migration grants `CREATE` only inside the atomic ownership-transfer
  statement, transfers both fixed-search-path functions, and revokes the
  capability on success and exception paths.
- The private executor remains NOLOGIN/non-super/non-inheriting, has no
  bypass-RLS or unexpected memberships, and retains no schema `CREATE`.
- Non-super `0042 → 0043 → 0042 → 0043`: 1 passed in 4.17s.
- Migration round-trip, catalog/ACL, API/gateway, and lifecycle checks:
  5 passed in 30.35s.
- Migration-chain unit: 1 passed in 2.24s.

The final complete PostgreSQL rerun remains pending.

## P11D — frontend and persona coverage

- All 14 original Chromium failures were repaired as stale strict tenant-feature
  fixtures/current Employee 360 selectors. Every failed node has a latest
  focused pass.
- Added 15 grouped tests across six Phase 11 specs for all 17 previously
  untouched tenant routes. They cover document-type management, own
  leave/cancel, manager approval scope, leave policy immutability, privacy
  evidence, retention/readiness, report masking/private object downloads,
  atomic employee import, privileged direct-route denials with zero privileged
  API calls, self-service, document-request resolution, and critical
  announcements. Every added case has a latest focused pass.
- Added one PWA boundary case:
  - `npx playwright test tests/pwa-cache-boundary.spec.ts`
  - 1 passed in 1.0m using the disposable Chromium installation.
  - Two authenticated API requests both reached the network, the API URL was
    absent from Cache Storage, and `/sw.js` carried `no-store` and root scope.
- TypeScript typecheck and ESLint over all changed/new E2E files are green.

The final configured Chromium run is intentionally reserved for P11F.

## P11E — security and dependency evidence

- `uv lock --check`: passed.
- Backend installed dependency audit:
  - no known vulnerabilities under strict `pip-audit`.
- Frontend production audit:
  - 0 vulnerabilities.
- Verified `detect-secrets` scan:
  - zero verified findings.
- Independent tracked-file credential/private-key pattern scan:
  - 697 files checked; zero credential-like filenames, private keys, or live
    AWS/GitHub/OpenAI/Slack/Stripe token patterns.
- Recovery CLI unit/guard lane:
  - 5 passed.
  - Exact command surface is `backup`, `verify-backup`, `restore-proof`, and
    `rollback-guard`; confirmation and isolated-target guards are present.

### Document upload/object boundary

- `uv run pytest -q backend/tests/test_employee_document_security.py`
  - 6 passed in 4.86s.
- The focused lane proves fail-closed runtime composition, tenant/employee/
  document/intent object-key metadata binding, cross-tenant and wrong-employee
  finalize/download denial, pending/infected/scanner-error non-downloadability,
  clean-only grants, and response/audit URL/key redaction.
- Demonstrated P2 fix: upload initiation serialized a server-default
  `created_at` immediately after flush and raised async `MissingGreenlet`.
  Refreshing the parent document before audit/response now preserves the
  critical upload journey.

### Reporting, export, and import boundaries

- `uv run pytest -q backend/tests/test_reporting_security.py
  backend/tests/test_command_idempotency.py
  backend/tests/test_import_boundaries.py`
  - 39 passed in 6.00s; the new focused module contributes 5 cases.
- The lane proves tenant-isolated report scope, manager-team versus HR-tenant
  scope, fail-closed sensitive-field policy, export owner/tenant BOLA,
  private short-lived download metadata with no bearer/cookie/object-key leak,
  import-preview owner/tenant BOLA and non-mutation, atomic invalid-row
  rollback, cross-tenant commit denial, and exactly-once replay.
- Demonstrated P2 fix: SQLite faithfully exposed that persisted timezone-aware
  export/import timestamps can be returned without `tzinfo`. Direct comparisons
  then crashed otherwise-valid job reads/downloads and import reads/commits.
  Response and comparison boundaries now normalize persisted values to UTC;
  PostgreSQL-aware values retain their instant.

### Self-service, announcements, notifications, and privacy

- `uv run pytest -q backend/tests/test_phase7_self_service_boundaries.py
  backend/tests/test_privacy_service_boundaries.py`
  - 6 passed in 3.35s.
- The focused lane proves server-resolved document-request targets, own/team/
  tenant projection boundaries, announcement role-recipient snapshots and
  recipient-only acknowledgement, actor/tenant-scoped notification state,
  current-version/hash privacy-notice acknowledgement, immutable own-only
  consent grant/withdraw evidence, and tenant-bounded count-only retention
  dry-run with no deletion.
- Demonstrated P2 fix: the `OutboxEvent.created_at` model used raw
  `text("now()")`, which made critical-announcement publication fail under
  supplementary SQLite with `unknown function: now()`. `func.now()` compiles
  to PostgreSQL `now()` and SQLite `CURRENT_TIMESTAMP`; migration `0039`
  remains semantically identical and no schema migration is required.

### Synthetic PostgreSQL recovery and rollback proof

The proof used only the disposable PostgreSQL 17 cluster and a private
0700 `/opt/data/tmp/ik-p11-*` root. Every DSN remained `[REDACTED]`. The source
was upgraded to head `0043`; it contained 70 public base tables, 66 with RLS.

- `scripts/ops/recovery.py backup` completed successfully:
  - one exact backup directory, three 0600 artifacts;
  - custom dump size 570,765 bytes;
  - SHA-256
    `25c48770534c5f88b6e9c2d5ff55c4fb215d4f0f2f0bebe90e056346bd76bf3a`;
  - manifest schema 1 and migration head `0043`;
  - object-storage status `not_applicable` because the synthetic proof
    explicitly disabled that backend.
- `verify-backup` independently verified the exact backup.
- Restore without `--confirm-isolated-restore` failed closed with
  `RESTORE_GUARD_REJECTED` and created no database.
- Confirmed `restore-proof` succeeded in 1.286 seconds:
  - restored migration head `0043`;
  - restored 70 public tables and 66 RLS-enabled tables;
  - object count/bytes were zero and status was `not_applicable`.
- `release_manifest.py` produced two valid manifests with distinct synthetic
  40-hex commits and the same application version/migration head.
- `rollback-guard` returned `safe_for_application_rollback: true`.
- The exclusive proof role had no superuser, role-creation, replication,
  bypass-RLS, membership, or inherited capabilities. The proof database,
  temporary role, backup/manifests, and private root were all removed; catalog
  verification found zero residual proof databases or roles.

This is local synthetic logical-backup/application-rollback evidence, not
staging/production deployment, WAL/PITR, object-store restore, or
cross-store-atomicity evidence.

## Residual gap report

Pending final acceptance. No residual is classified until the real PostgreSQL,
security/recovery, final backend, final frontend, and final Chromium gates have
completed. Staging deployment and merge remain supervisor-owned.
