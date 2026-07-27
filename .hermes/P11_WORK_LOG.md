# Phase 11 Work Log

Status: complete — all required local Phase 11 gates have current green
evidence; staging acceptance and merge remain supervisor-owned
Started: 2026-07-27T13:03:41Z
Finished: 2026-07-27T15:54:19Z
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
| P11B backend regression | complete | Final complete default lane: 1,072 passed / 74 PostgreSQL deselected; Ruff, formatter, 177-operation OpenAPI registry, and 80-endpoint runtime smoke green | Authorization catalog serialization, dashboard UTC projection, current lifecycle/profile fixtures/contracts, migration compatibility harness, leave lineage/date validation, and architecture boundaries |
| P11C PostgreSQL/RLS | complete | Final PostgreSQL 17.10 lane: 73 passed / 1 historical fixture failure; scoped fixture repair node then passed, making all 74 cases green | Current P6 SQL fixtures, privacy model default drift, guarded downgrade remediation, session-policy selection, tenant FK fixtures, archive/profile locking/race, non-super migration ownership, and performance data |
| P11D frontend/E2E | complete | Frozen install, production audit, typecheck, lint, build, and 52-case inventory green; complete Chromium 51 passed / 1 selector failure, then repaired spec 1 passed | Strict feature fixtures, current Employee 360 contracts, authorization selectors, 17 previously untouched routes, PWA cache isolation, and unambiguous status assertion |
| P11E security/performance | complete | Production dependency and secret scans green; 10k PostgreSQL plan proof, document/object boundary, and synthetic PostgreSQL backup/restore/rollback proof green | Current performance fixtures, upload/report/privacy boundaries, PWA authenticated-data cache proof, and real PostgreSQL recovery evidence |
| P11F final/report | complete | Tested product checkpoint and two test-only follow-ups pushed; local complete gate green after affected reruns; remote candidate SHA and cleanup verified | Evidence-backed residual report |

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

Dashboard and leave-balance focused confirmation passed 25 cases in 59.51s;
the complete default lane also passed.

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
  corrected and confirmed by the subsequent affected/default lanes.

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

Final complete-lane result:

- `IK_TEST_DATABASE_URL=[REDACTED] uv run pytest -q -m postgres`
  - 73 passed, 1 failed, 1,072 deselected, 11 warnings in 194.65s.
  - The only failure was test-harness drift: the P0E downgrade probe
    intentionally moves to revision `0012`, but the newly required current
    gateway identity seed was initially unconditional and therefore referenced
    the later `identities` table.
- The identity/membership/role seed is now scoped to current-contract fixtures.
  The affected historical node passed 1/1 in 6.50s.
- Thus all 74 collected PostgreSQL cases have current passing evidence. The
  final complete command was not repeated after a test-only repair, in
  accordance with the Phase 11 broad-suite budget.

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

Final frontend evidence:

- `npm ci`: 352 packages installed from the lockfile.
- `npm audit --omit=dev --audit-level=high`: 0 production vulnerabilities.
- `npm run typecheck` and `npm run lint`: passed.
- `npm run build`: Next.js 16.2.12 production build passed; 34 static pages.
- `npx playwright test --list`: 52 Chromium cases across 22 files.
- Complete `npx playwright test`: 51 passed / 1 failed in 2.7 minutes.
  - The product correctly showed creation success while a reload status was
    transiently present. The new test used an ambiguous global `role=status`
    locator and failed Playwright strict mode.
  - Both creation/archive assertions now filter status by their exact success
    message. Targeted ESLint passed and the affected spec passed 1/1 in 42.3s.
  - The complete browser command was not repeated after this test-only selector
    repair; all 52 cases have current passing evidence.

## P11E — security and dependency evidence

- `uv lock --check`: passed.
- Backend installed dependency audit:
  - no known vulnerabilities under strict `pip-audit`.
- Frontend production audit:
  - 0 vulnerabilities.
- Tracked-file `detect-secrets` scan:
  - 719 tracked files scanned;
  - 311 heuristic candidates across 51 files: 244 hexadecimal entropy, 55
    keyword, 11 basic-auth syntax, and 1 base64 entropy;
  - the seven production/script candidates were inspected as error-message
    identifiers, a local dummy DSN, audit enum identifiers, secure token-module
    imports, a fixed dummy Argon2 timing hash, and a synthetic trace ID;
  - remaining candidates are deterministic tests/contracts/documentation
    examples. Zero live or verified secrets.
- Independent high-confidence tracked-file scan:
  - 719 files checked; zero credential-like filenames, private keys, or live
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
- A bounded repair-diff audit found the same P2 portability defect in the newly
  aligned `PrivacyConsentPurpose.created_at` default. It now also uses
  `func.now()`; the SQLite privacy seed intentionally omits that field and the
  same 6-case lane passes. Dialect compilation is PostgreSQL `now()` and SQLite
  `CURRENT_TIMESTAMP`, preserving migration `0041` semantics.

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

## P11F — final local gate and immutable candidate

Final inventory is 1,146 backend cases: 1,072 default and 74 PostgreSQL.
Playwright contains 52 Chromium cases across 22 files. The product repair
checkpoint is `8625839836013f6ec5d4dadff86bd2ddcad678f8`; the only later code-tree
changes are two test-only harness corrections. The final locally tested/pushed
candidate before this evidence-only log update is
`08d659ca21801fad464073128c31e04fda243681`.

### Static, default backend, and runtime contract

- `uv run ruff check backend scripts`: passed.
- `uv run ruff format --check backend scripts`: 361 files already formatted.
- The excluded new forward migration was checked explicitly: 1 file already
  formatted. No historical migration changed.
- `uv lock --check`: passed; 55 packages resolved from the frozen lock.
- `uv run pytest -q --lf`
  - The stale cache contained no matching failed nodes, so pytest's documented
    no-failures fallback executed the entire default lane.
  - 1,072 passed, 74 PostgreSQL cases deselected, 1 dependency deprecation
    warning, in 683.66s.
- `uv run python scripts/backend_api_smoke.py`
  - `BACKEND_SMOKE_OK`;
  - 80 documented endpoint tables exercised;
  - exact 142 paths / 177 operations / 381 schemas retained.

### PostgreSQL

- Complete lane and its one test-only historical fixture correction are
  recorded under P11C: 73/74 passed in the broad run, then the affected node
  passed in 6.50s, yielding current green evidence for all 74 cases.
- Migration head is the single linear
  `0043_p11_employee_lifecycle_profile_lock`.
- The representative 10k/5k query-plan case, non-super migration-owner
  round-trip, RLS/ACL/tenant isolation, concurrency, drift, downgrade, and API
  smoke cases all passed in the complete command.

### Frontend and Chromium

- Frozen install, 0-vulnerability production audit, typecheck, lint, and
  production build passed.
- Playwright inventory: 52 cases / 22 files.
- Complete Chromium: 51 passed / 1 selector-only failure in 2.7 minutes;
  repaired affected spec: 1 passed in 42.3s. All 52 cases therefore have
  current passing evidence without repeating the broad browser command.

### Release candidate

- `scripts/ops/release_manifest.py` generated a schema-valid manifest for
  `08d659ca21801fad464073128c31e04fda243681`.
- App version `0.1.0`; compatible migration head
  `0043_p11_employee_lifecycle_profile_lock`.
- `sha256sum --check --strict` passed; final verified manifest SHA-256:
  `2130642f48f3e95af5b7d096b6022202ffaf31131feb087f049268e0f7f22155`.
- The disposable release-manifest directory was removed.
- `git ls-remote` matched local and remote candidate SHA
  `08d659ca21801fad464073128c31e04fda243681` before this evidence-only
  log commit.
- The disposable PostgreSQL server was stopped; its exact cluster root, the
  Chromium installation, recovery/security/release proof roots, collection
  output, `.next`/Playwright artifacts, Ruff/pytest caches, and Python bytecode
  caches were removed. Final `/opt/data/tmp/ik-p11-*` count: zero.

## Residual gap report

### MVP blockers

None open. No demonstrated tenant leak, authorization bypass, data
loss/corruption, migration break, secret exposure, or broken critical journey
remains.

### Safe post-MVP gaps

- Physical retention deletion/anonymization execution, legal-hold
  orchestration, and DSAR/data-subject request packages remain the plan's
  explicit post-MVP scope. The MVP exposes only a tenant-bounded count-only
  retention dry-run; there is no destructive endpoint that can bypass a hold.
- The complete npm tree reports nine high advisories confined to ESLint and
  plugin/transitive development tooling. The production tree has zero
  vulnerabilities. npm proposes unsafe major/downgrade changes rather than a
  compatible fix; this is build-tool dependency debt, not shipped runtime
  exposure.
- Starlette emits one dependency deprecation warning for its current TestClient
  HTTP client integration. It does not affect the validated runtime behavior.
- The local recovery proof is logical PostgreSQL backup/restore and application
  rollback compatibility. WAL/PITR, real object-store restoration,
  cross-store atomicity, and staging/production restore drills require the
  supervisor-owned environment.
- Query-plan evidence is representative synthetic evidence, not a fabricated
  production SLO.

### Environment-owned acceptance

- The repository Quality workflow runs on pull requests, `main`, or manual
  dispatch, not an ordinary branch push. No branch CI run is expected without a
  supervisor-owned PR/manual dispatch.
- Staging deployment, four-process staging identity, staging smoke, lock
  release, immutable staging manifest verification, merge, and production
  deployment remain supervisor-owned and were not performed.
