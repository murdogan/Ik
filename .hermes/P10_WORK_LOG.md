# Phase 10 Work Log

## Release identity

- Branch: `codex/mvp-phase10-pilot-readiness`
- Base main SHA: `ce21975c291bfc2a9b2ab79c86e636f86c03d1a1`
- Phase 10 plan checkpoint: `a83626b27787422dd8cc5a4235edddc2858419b3`
- Database head entering Phase 10: `0042_p9_privacy_evidence_hardening`
- Migration policy: no Phase 10 migration unless a persistent schema change becomes necessary.

## P10A — Baseline and isolation

Status: complete.

- Dedicated worktree: `/opt/data/repos/Ik-mvp-phase10`
- Production-only Codex isolation established without tests, fixtures, credentials, historical reports, or migration history.
- Codex catalog and startup banner verified for `gpt-5.6-sol`, reasoning `ultra`.
- The host kernel rejected the normal bubblewrap namespace; the Codex run used danger-full-access only inside the physically isolated production workspace.

## P10B — Tenant setup readiness

Status: implementation and focused verification complete; checkpoint commit pending at the time of this entry.

### Delivered

- Session-derived, permission-gated `GET /api/v1/tenant/readiness`.
- Fixed nine-item tenant setup-readiness projection.
- Single bounded aggregate/`EXISTS` query with tenant predicates on tenant-owned data.
- Strict backend and frontend response validation.
- Protected `/setup` tenant workspace with retry/error states and permission/feature-gated remediation links.
- Tenant navigation and proxy integration.
- Additive OpenAPI metadata.

### Authorization and privacy

- Existing `organization:update:tenant` permission is used consistently by backend, route layout, fetch/render logic, and navigation.
- No new permission or migration was added.
- Tenant, actor, and membership come from the validated live session; client tenant headers do not select scope.
- Response contains aggregate counts/status only and exposes no employee/user/document/notice identity, provider detail, DSN, secret, or storage/scanner mode.

### Attribution

- Production vertical authored by Codex CLI using `gpt-5.6-sol` with `ultra` reasoning.
- Product decisions, isolated context, mechanical Ruff formatting, OpenAPI tag metadata correction, integration, security review, and verification performed by Hermes.

### Verification evidence

Passed:

- Backend Ruff lint and format check.
- Python compile.
- Generated OpenAPI security/response/schema checks.
- Frontend TypeScript typecheck and ESLint.
- SQLite `Base.metadata.create_all()` and real readiness aggregate execution.
- Anonymous and spoofed-tenant-header deny smoke (`401`).
- `git diff --check` and unexpected-file hygiene.
- Independent inspect-only security/access-control review: no blocking critical/high/medium/low finding.

Known baseline test drift, not caused by P10B:

- Existing tenant API fixtures omit the already-required `leave_requests.leave_type_id` and fail during fixture commit before P10B execution.
- Existing OpenAPI metadata tests expect stale summaries/descriptions/error examples from earlier phases.
- These broad historical fixture/snapshot repairs remain in Phase 11 regression/repair scope.

## P10C — Operational readiness and signals

Status: implementation and focused verification complete; checkpoint commit pending at the time of this entry.

### Delivered

- Backward-compatible legacy `/health` plus public constant-time `/health/live`.
- Bounded database-only `/health/ready` with generic 200/503 component state and no-cache headers.
- Strict immutable release SHA/build timestamp validation with staging/production fail-fast behavior.
- Dedicated idempotent one-line JSON operational logger with finite field allowlists.
- Correlated request completion signals using code-owned route templates, without raw path/query/body/header or tenant/user/session identifiers.
- Rate-limited notification/reporting worker start, heartbeat, failure, and stop signals; identifier-bearing legacy worker log fields scrubbed.

### Attribution and verification

- Production implementation authored by Codex CLI using `gpt-5.6-sol` with `ultra` reasoning.
- Contract, isolation, mechanical Ruff formatting, integration, security inspection, and verification performed by Hermes.
- Passed targeted Ruff lint/format, Python compile, generated runtime import, exact legacy health payload, live 200, readiness 200/503, no-cache headers, route-template JSON output, and PII-field absence smoke.
- No tests were added and no broad test/build suite was run.

## P10D — Secure PWA and mobile hardening

Status: implementation and focused verification complete; checkpoint commit pending at the time of this entry.

### Delivered

- Installable Turkish App Router manifest with valid 192/512/maskable PNG icons.
- Production-only service-worker registration and exact no-cache/worker-scope headers.
- Finite service-worker cache allowlist limited to same-origin hashed Next static assets and explicit icons; navigation, HTML, API, auth, tenant content, uploads, and documents are never intercepted or cached.
- Standalone safe areas, reduced-motion handling, 16px narrow-touch form controls, visible focus, and targeted 320px fixes for tenant navigation, leave, self-service, profile/documents, and setup readiness surfaces.

### Attribution and verification

- Production implementation authored by Codex CLI using `gpt-5.6-sol` with `ultra` reasoning.
- Contract, isolation, integration, service-worker security inspection, and verification performed by Hermes.
- Passed TypeScript, ESLint, service-worker syntax, PNG signature/dimension, dependency-integrity, and diff hygiene checks.
- No tests were added and no broad test/build suite was run.

## P10E — Recovery proof tooling

Status: implementation and focused static verification complete; checkpoint commit pending at the time of this entry.

### Delivered

- Stdlib-only fail-closed recovery CLI with `backup`, `verify-backup`, `restore-proof`, and `rollback-guard` commands.
- Private custom-format PostgreSQL backups, canonical manifests/checksums, optional preconfigured-`mc` object mirror, strict path/mode/symlink controls, secret-free subprocess environment, and bounded execution.
- Restore proof restricted to a separately named disposable `*_restore_proof` database with explicit acknowledgements and mandatory cleanup; source restore and migration downgrade are forbidden.
- Read-only release rollback compatibility guard and detailed Turkish operator runbook with stop/escalation rules.

### Attribution and verification

- Production implementation authored by Codex CLI using `gpt-5.6-sol` with `ultra` reasoning.
- Contract, correction of the Alembic revision grammar to `[0-9a-z_]+`, integration, security inspection, and verification performed by Hermes.
- Passed Python compile, Ruff lint/format, all four command help probes, generic fail-closed output smoke, and diff hygiene.
- No tests were added, no broad suite was run, and no service connection or destructive operation occurred during implementation.

## P10F — Active CI and immutable release identity

Status: implementation and focused verification complete; checkpoint commit pending at the time of this entry.

### Delivered

- First active least-privilege GitHub Actions quality workflow for backend static/OpenAPI/Alembic-head checks, frontend typecheck/lint/build, and immutable release artifact generation.
- Canonical strict release manifest plus checksum generator using repository app version and database-free Alembic head discovery; schema is compatible with the P10E rollback guard.
- Staging deploy preflight now generates and validates private release artifacts before stopping the current process, injects validated release SHA/timestamp into Uvicorn, and gates startup on `/health/ready` with exact commit matching.
- Full pytest regression and Playwright/E2E are explicitly deferred to Phase 11 after historical fixture/snapshot repair rather than represented by a fake green job.

### Attribution and verification

- Production implementation authored by Codex CLI using `gpt-5.6-sol` with `ultra` reasoning.
- Contract, integration, CI/deploy security inspection, and verification performed by Hermes.
- Passed release generator Ruff/compile/help, deploy shell syntax, workflow YAML parse, real repository Alembic-head manifest generation, checksum/schema verification, and diff hygiene.
- No tests were added, no broad suite/build was run locally, and no deployment or GitHub Actions invocation occurred.

## P10G — Pilot release candidate, staging acceptance, and Phase 11 handoff

Status: complete; Phase 11 handoff ready.

### Immutable release identity

- Phase 10 runtime release candidate: `75baff18a0a1e62ea8ce4c1af39e0f41742e3e7f`.
- Release manifest: `/opt/data/staging/ik-releases/75baff18a0a1e62ea8ce4c1af39e0f41742e3e7f-20260726T121020Z-689845/release-manifest.json`.
- Release manifest SHA-256: `ab3c6c83eb328c8e4eb12b0611a4341c6e689d0212bcc2383f5a6146023bec64` (`204` bytes).
- Compatible migration head: `0042_p9_privacy_evidence_hardening`.
- GitHub Actions Quality run: `30201447331`, conclusion `success` on the exact runtime RC.
- RC authorship: Codex authored P10B–P10F production verticals; Hermes authored integration, migration URL correction, recovery/deploy hardening, dependency security update, staging acceptance, and checkpoint evidence.

### Final focused gates

Passed:

- Recovery/migration focused pytest: `10 passed`.
- Changed recovery/migration Ruff lint and scoped format check.
- Deploy Bash syntax, direct executable PID/static guard, and `git diff --check`.
- Frontend TypeScript, ESLint, and Next.js `16.2.12` production build under a bounded `512 MiB` Node heap.
- Exact RC production dependency audit: `npm audit --omit=dev` reported `0 vulnerabilities`.
- GitHub Actions backend quality and frontend quality both passed.

A staging audit discovered newly published high-severity advisories affecting Next.js `16.2.10` and its production transitive dependencies. Phase 10 was reopened, Next.js and `eslint-config-next` were updated to `16.2.12`, and patched `postcss 8.5.23` / `sharp 0.35.3` overrides were locked before the final RC was accepted. The remaining all-dependency audit findings are confined to ESLint/build tooling; they are not present in `--omit=dev` runtime dependencies and are recorded for maintenance rather than represented as a runtime pass.

### Backup and restore evidence

- Real staging backup: `/opt/data/staging/p10g-recovery/backup-20260718T102002Z-ba919bfb`.
- Backup completion: `2026-07-18T10:20:03Z`, status `completed`.
- PostgreSQL archive: `552507` bytes.
- Backup manifest: `540` bytes; SHA-256 `586773f72d9cb90bead8ffc17b38174baff9822a7d797d1cdea6052b3419323b`.
- PostgreSQL 17 disposable restore proof passed with `70` restored tables, migration head `0042_p9_privacy_evidence_hardening`, `66` RLS-enabled tables, and proof database/role cleanup.
- Synthetic object proof passed with one object (`35` bytes), a dedicated empty non-production bucket, explicit `--confirm-synthetic-object-data`, aggregate-only verification, and post-proof remote cleanup.
- The object proof now fails closed unless include flag, synthetic-data acknowledgement, alias, and bucket are supplied together; a non-empty proof target is rejected.

### Staging acceptance

Exact SHA `75baff18a0a1e62ea8ce4c1af39e0f41742e3e7f` is deployed from the pushed review branch:

- API PID `690258` — alive, persisted starttime and release identity matched.
- Web PID `690261` — alive, persisted starttime and release identity matched.
- Notification worker PID `690270` — alive, persisted starttime and release identity matched.
- Reporting worker PID `690274` — alive, persisted starttime and release identity matched.
- Duplicate workers left from the Phase 9 checkout were identity-checked and stopped before final acceptance.
- API readiness: `200`, database `ready`, exact commit identity matched.
- Web root: `200`; authenticated `/dashboard` guard: `307`.
- Anonymous tenant-readiness API guard: `401`.
- PWA manifest and service worker: `200`; static-asset-only cache policy remains unchanged.
- Alembic current: `0042_p9_privacy_evidence_hardening (head)`; `alembic check`: no new upgrade operations.
- PostgreSQL evidence: `66` RLS-enabled tables and `105` public-schema policies.
- Temporary public web: `https://excel-nor-besides-passengers.trycloudflare.com` (`/` `200`, `/dashboard` `307`, manifest/service-worker `200`).
- Temporary public API: `https://supervision-saint-aurora-syracuse.trycloudflare.com` (`/health/live` `200`, `/health/ready` `200` with exact RC identity, anonymous readiness `401`).

Bounded independent reviews found and drove closure of stale/reused PID termination, PID-file write leakage, inherited deploy-lock FD, and pre-capture child leakage. Final RC `75baff18a0a1e62ea8ce4c1af39e0f41742e3e7f` launches each service inside a pidfd-holding Python launcher: identity capture, role/release validation, complete atomic PID identity writes, and parent-directory durability complete before ownership returns to the deploy shell; capture/validation/write failures terminate and mandatorily wait/reap that exact child. Failure injection proved successful launch-record-verify-stop, capture-timeout cleanup, and atomic-write-failure cleanup. Exact-RC CI, real staging cutover, final identity checks, and post-deploy `flock` acquisition passed.

Both public URLs are accountless Cloudflare quick tunnels and therefore temporary staging evidence only; they are not stable pilot-production ingress.

### Residual risks and Phase 11 handoff

- Staging deploy performs all build/preflight work before cutover and cleans newly started processes on failure, but the final process cutover is not blue/green or atomic. This is an accepted staging operational residual, not a production deployment approval.
- Stable named ingress, production deployment, and production secrets/provider enablement were not authorized and were not performed.
- Phase 11 owns the intentionally deferred full backend/PostgreSQL regression, broad Playwright persona journeys, complete role × scope × endpoint authorization matrix, all-table tenant isolation/BOLA matrix, prior-phase concurrency/idempotency regression, malformed frontend projection matrix, representative performance/query-plan checks, and demonstrated-defect repair/rerun loops.
- Phase 10 merge does not constitute MVP acceptance; MVP completion remains the end of Phase 11.
