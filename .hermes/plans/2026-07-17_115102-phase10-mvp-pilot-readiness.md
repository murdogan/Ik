# Phase 10 — MVP Pilot Readiness and Operational Hardening Implementation Plan

> **For Hermes:** Use `software-development/phase-gated-product-development` and the applicable security/operations references to implement this plan block-by-block. Continue through P10A–P10G without sub-block approval unless a real blocker or an explicit product/security decision is reached. Phase 10 uses narrow quality, migration, and product smoke gates; Phase 11 owns exhaustive E2E/regression/security testing and demonstrated-defect repair.

**Goal:** Turn the Phase 9-complete MVP into a pilot-ready product that a tenant can safely initialize, install/use on mobile, operate, observe, back up, restore, and release from an immutable `main` SHA without adding V1 product modules.

**Architecture:** Preserve the existing FastAPI + SQLAlchemy/Alembic + PostgreSQL + Next.js modular monolith. Add a tenant-safe readiness projection and workspace, secure installable-PWA metadata without offline caching of authenticated HR data, structured PII-free operational signals, reproducible backup/restore and release preflight tooling, and an active CI quality boundary. Do not create a generalized workflow engine, Kubernetes platform, enterprise observability stack, or privileged support impersonation framework.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17, Next.js 16, TypeScript, existing worker processes, GitHub Actions, Cloudflare named-tunnel/domain as an external pilot deployment prerequisite.

**Planning base:** `ce21975c291bfc2a9b2ab79c86e636f86c03d1a1` (`main == origin/main`, 2026-07-17)

---

## 1. Authoritative sources and scope reconciliation

This plan is derived from:

- `.hermes/plans/2026-07-10_122125-mvp-first-release-master-development-plan.md`
- `docs/08-yurutme/01-roadmap-fazlar-milestone.md`
- `docs/02-urun/03-mvp-v1-v2-kapsam-kararlari.md`
- `docs/07-operasyon/01-devops-ortamlar-surum-yonetimi.md`
- `docs/07-operasyon/02-observability-slo-alarm.md`
- `docs/07-operasyon/03-test-stratejisi-qa.md`
- `docs/07-operasyon/04-runbook-operasyon-surecleri.md`
- `/opt/data/project_states/ik-operasyon-protokolu.md`
- `/opt/data/project_states/ik-proje-kurallari-ve-kritik-notlar.md`

The master feature plan defines API feature surfaces through Phase 9. The roadmap’s next remaining MVP milestone is S8 **Pilot hardening**, while the MVP release definition requires pilot data import, tenant isolation, backup/rollback, onboarding, and support readiness. Therefore Phase 10 is operational/product hardening rather than another HR domain module.

### Platform-support discrepancy

The early master plan listed JIT/break-glass support-access endpoints under Phase 9, but the accepted Phase 9 delivery intentionally shipped the privacy/compliance vertical and did not introduce customer-data impersonation. Phase 10 must not silently add a privileged bypass.

Default Phase 10 decision:

- Platform operators remain unable to read tenant HR payloads.
- Pilot support uses tenant-admin actions, screenshare, tenant-safe metadata, and audited operational diagnostics.
- Full JIT/break-glass customer-data access remains out of scope until platform MFA/step-up, customer approval policy, dual-visible audit, automatic expiry, and a dedicated security review are approved as one coherent boundary.
- If Murat explicitly chooses full support access before implementation, create a separate security design checkpoint before P10A; do not let Codex infer it.

---

## 2. Product outcome

At the end of Phase 10:

1. A tenant admin sees a concrete setup/readiness checklist instead of discovering missing setup through failures.
2. Platform and tenant users see only readiness metadata they are authorized to see; no cross-tenant or HR payload leakage is introduced.
3. The web app is installable as a branded PWA, but authenticated pages, API responses, documents, exports, and PII are never cached offline.
4. API/web/worker logs are structured, correlated, bounded, and PII-free.
5. Liveness and readiness checks distinguish “process alive” from “dependencies usable” without exposing secrets or internal topology publicly.
6. PostgreSQL and object-storage backup procedures produce checksummed artifacts and a disposable restore verification proves recoverability.
7. Pull requests and `main` pushes have an active quality workflow; deployment remains manual and approval-controlled.
8. A release-preflight command binds source SHA, migration head, build, configuration mode, dependency readiness, and rollback metadata into one machine-readable release manifest.
9. A pilot deployment uses an immutable `origin/main` SHA and a stable named tunnel/domain. A quick `trycloudflare.com` tunnel is not accepted as durable pilot production.
10. Phase 11 receives a versioned release candidate and explicit deferred test matrix rather than an unstable moving target.

---

## 3. In scope

### Must

- Tenant setup/readiness projection and tenant-admin workspace.
- Safe liveness/readiness/version endpoints.
- PII-free structured API and worker operational logging.
- Secure installable PWA metadata and offline-cache deny policy.
- PostgreSQL backup + disposable restore verification.
- Object-storage inventory/backup verification procedure for document artifacts.
- Release preflight and immutable release manifest.
- Active GitHub Actions quality workflow without deployment secrets.
- Pilot deployment/rollback runbook synchronized with actual commands.
- Narrow PostgreSQL/authorization/product smoke and staging acceptance.

### Should

- Worker freshness/queue-health metadata in readiness without exposing job payloads.
- Tenant-admin readiness deep links to the exact setup screens.
- Frontend offline/error shell that contains no tenant data.
- Release notes generated from an explicit version/SHA rather than runtime guesswork.

### Could, only if low-risk after Must/Should

- Prometheus-compatible metrics endpoint restricted to internal/explicitly configured access.
- Synthetic read-only pilot health probe.
- Minimal deployment observation summary for backup age, worker freshness, and migration head.

---

## 4. Explicitly out of scope

- Detailed all-persona Playwright matrix, broad regression, exhaustive tenant/RLS matrix, and repair campaign — Phase 11.
- Native payroll, SGK, bank file generation, PDKS/shift engine, ATS, performance/OKR, LMS, AI, webhooks, SSO/SCIM/SIEM.
- Physical retention deletion, anonymization worker, DSAR/DSR export package, or irreversible privacy lifecycle execution.
- Offline access to employee, leave, document, report, privacy, audit, or notification data.
- Push notifications.
- Kubernetes, Helm, GitOps, multi-region DR, PITR platform implementation, or enterprise monitoring stack deployment.
- Customer-data support impersonation/JIT break-glass without the separate approved MFA/security boundary.
- Storing credentials, DSNs, tokens, cookies, document content, or employee payloads in release manifests, CI artifacts, logs, or backup metadata.
- Auto-deploy from `main`; merge/deploy remains Murat-approved.

---

## 5. Security and data boundaries

1. `tenant_id`, actor identity, and membership are session-derived; readiness requests cannot submit them in payloads.
2. The tenant readiness endpoint is tenant-scoped and permission-protected. Platform operators receive only platform-owned release/deployment metadata, not tenant setup counts.
3. Any new tenant table receives `tenant_id`, relational integrity, explicit RBAC, RLS + FORCE RLS, least-privilege grants, and value-minimized audit.
4. Prefer a read-only derived projection over a new persistent table. Do not create schema merely to cache counts.
5. Readiness responses contain bounded booleans/counts and remediation keys; no names, emails, document titles, consent choices, raw audit metadata, or employee identifiers.
6. Public liveness returns only generic status/version. Dependency readiness details are internal or authorization-protected and never reveal hostnames, ports, bucket names, SQL errors, or provider credentials.
7. Logs use trace/request IDs, route templates, status, duration, service, environment, and safe event keys. Query strings, request/response bodies, cookies, authorization headers, raw user IDs, and PII are forbidden.
8. PWA service-worker logic must explicitly bypass `/api/`, authenticated route HTML, download/presign URLs, documents, exports, and responses with `Cache-Control: no-store` or credentials.
9. Backup artifacts are encrypted/permission-restricted at the environment layer; repository tooling records only path, time, size, checksum, source version, and migration head.
10. Restore verification always targets a disposable database/bucket namespace and refuses staging/prod targets by default.

---

## 6. Migration strategy

Default: **no database migration is required** for readiness projection, logging, PWA, CI, backup tooling, or release manifests.

- Current head remains `0042_p9_privacy_evidence_hardening` unless implementation discovery proves persistent state is essential.
- Derived readiness must query current bounded tenant tables and reuse existing indexes/permissions.
- Do not mutate `0041` or `0042`.
- If a concrete persistent requirement is approved, use additive revision:
  - `0043_p10_pilot_readiness`
  - no destructive changes;
  - no tenant data reinterpretation;
  - explicit RLS/FORCE RLS and privilege matrix;
  - proportional migration only;
  - clean `base → head`, `0042 → 0043 → 0042 → 0043`, and metadata drift proof.
- Multiple top-level DDL statements must not be sent in one asyncpg `op.execute()`.

---

## 7. Delivery blocks

## P10A — Baseline, release contract, and support boundary

**Objective:** Freeze Phase 10’s release contract and prevent hidden scope expansion before code generation.

**Read/inspect:**

- `backend/app/core/config.py`
- `backend/app/api/health.py`
- `backend/app/main.py`
- `backend/app/platform/observability/`
- `frontend/src/app/layout.tsx`
- `frontend/src/proxy.ts`
- `docs/07-operasyon/01-devops-ortamlar-surum-yonetimi.md`
- `docs/07-operasyon/04-runbook-operasyon-surecleri.md`

**Actions:**

1. Create branch/worktree from verified `origin/main`:
   - branch: `codex/mvp-phase10-pilot-readiness`
   - worktree: `/opt/data/repos/Ik-mvp-phase10`
2. Record base SHA and confirm diff `0`.
3. Build a production-only Codex workspace containing production/config imports but no tests, fixtures, credentials, historical reports, runtime state, or `.env` files.
4. Record the support decision: no customer-data impersonation in Phase 10.
5. Inventory environment-owned decisions:
   - stable pilot domain/named tunnel;
   - real email provider for pilot or notifications explicitly disabled;
   - backup destination and encryption ownership;
   - whether internal metrics scraping is available.
6. Create a phase work log outside the production diff; do not commit secrets or temporary context.

**Focused gate:** branch/worktree/base SHA/forbidden-path proof only.

**Stop condition:** Any request to add privileged support access, real customer data, irreversible retention execution, or production credentials requires a separate decision before continuing.

---

## P10B — Tenant setup readiness projection and workspace

**Objective:** Give tenant admins a bounded, actionable readiness checklist for first pilot setup.

**Likely backend files:**

- Create: `backend/app/schemas/tenant_readiness.py`
- Create: `backend/app/services/tenant_readiness_service.py`
- Create: `backend/app/api/tenant_readiness.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/openapi.py`
- Modify: `backend/app/platform/authorization/catalog.py`
- Modify only if necessary: `backend/app/services/tenant_service.py`

**Likely frontend files:**

- Create: `frontend/src/lib/tenant-readiness.ts`
- Create: `frontend/src/components/setup/tenant-readiness-workspace.tsx`
- Create: `frontend/src/components/setup/tenant-readiness.module.css`
- Create: `frontend/src/app/(protected)/(tenant)/setup/page.tsx`
- Create: `frontend/src/app/(protected)/(tenant)/setup/layout.tsx`
- Modify: `frontend/src/components/dashboard/tenant-shell.tsx`
- Modify: `frontend/src/lib/authorization.ts`

**Readiness checks:**

- legal entity/default entity configured;
- organization structure has required root data;
- at least one active tenant administrator exists;
- employee master data exists or an import is ready/committed;
- leave type/policy/calendar minimum exists when leave feature is enabled;
- document type minimum exists when documents feature is enabled;
- active published privacy notice exists;
- enabled feature prerequisites are coherent;
- notification delivery mode is represented only as safe operational state, not provider credentials.

**Contract:**

- `GET /api/v1/tenant/readiness`
- Exact bounded response: overall state, checklist item key, state (`ready|action_required|not_applicable`), safe count where necessary, remediation route, and last-evaluated timestamp.
- No mutation endpoint; users fix setup in existing product screens.
- No platform-admin tenant HR visibility.

**Authorization:**

- New explicit permission, recommended `tenant:readiness:read`.
- Grant only tenant admin/HR administration roles justified by existing role catalog.
- Manager/employee/read-only direct route and API access denied.
- Rendering and fetch must both be permission-gated.

**UX:**

- Calm setup checklist, not a card-heavy marketing dashboard.
- Clear progress and direct links to existing setup screens.
- Distinguish loading, empty, authorization error, dependency error, and complete states.
- No celebratory “secure/ready” claims beyond measured checklist facts.

**Focused gate:** changed-code lint/typecheck, one authorized tenant-admin response, one employee denial, one second-tenant denial, one browser happy path with zero unauthorized management requests.

---

## P10C — Liveness, readiness, release identity, and PII-free operational signals

**Objective:** Make process/dependency state diagnosable without exposing infrastructure or personal data.

**Likely backend files:**

- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/health.py`
- Modify: `backend/app/platform/observability/correlation.py`
- Create: `backend/app/platform/observability/structured_logging.py`
- Create: `backend/app/platform/observability/readiness.py`
- Modify: `backend/app/main.py`
- Modify worker entrypoints under `backend/app/workers/`

**Endpoints:**

- Preserve `/health` compatibility.
- Add `/health/live`: process liveness only, constant-time, no dependency access.
- Add `/health/ready`: bounded DB/runtime readiness with generic component states.
- Add immutable release metadata from environment/build input: version, commit SHA, build timestamp; validate format and never infer from mutable git state at runtime.
- Detailed dependency reasons remain internal/log-only and redacted.

**Logging:**

- Structured JSON in staging/pilot/prod; developer-readable mode may remain local-only.
- Safe fields: timestamp, level, service, environment, trace ID, route template, method, status, duration, event/error code, release SHA.
- Hash user identity only if operationally necessary and with a configured non-auth secret; default omit.
- Worker cycle logs report bounded counts/duration/outcome without job payloads or tenant HR values.
- Suppress repetitive healthy-loop noise; health checks must not flood logs.

**Metrics:**

- Do not deploy Grafana/Prometheus in this block.
- If a metrics endpoint is implemented, make it disabled by default and internal/allowlisted; no tenant/user labels that cause PII or unbounded cardinality.

**Focused gate:** liveness succeeds during dependency health, readiness fails generically when disposable DB is unavailable, no secret/topology leakage, trace ID continuity, safe JSON log sample, healthy worker-loop noise bound.

---

## P10D — Secure installable PWA and mobile readiness

**Objective:** Deliver the roadmap’s basic mobile/PWA MVP without caching protected HR data.

**Likely files:**

- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/manifest.ts`
- Create: `frontend/public/icons/wealthy-falcon-192.png`
- Create: `frontend/public/icons/wealthy-falcon-512.png`
- Create: `frontend/public/offline.html` or a minimal public offline shell
- Create/modify a narrowly scoped service-worker registration module under `frontend/src/components/platform/`
- Modify: `frontend/src/app/globals.css`
- Inspect and adjust only demonstrated mobile defects in login, home, leave, approvals, profile, announcements, and privacy screens.

**Rules:**

- Cache only immutable static assets and the public offline shell.
- Network-only/no-store for `/api/**`, protected HTML, auth routes with session state, documents, exports, download intents, presigned URLs, audit, privacy evidence, notifications, and reports.
- Never persist access/refresh tokens or API payloads in service-worker caches, IndexedDB, localStorage, or Cache Storage.
- Offline mode must say connectivity is required; it must not display stale tenant data.
- Install metadata uses Wealthy Falcon HR branding and current design tokens.
- No push notification implementation.

**Focused gate:** production build, manifest/icon validity, installability smoke, offline shell, authenticated/API cache deny assertions, mobile viewport smoke for login + employee home + leave request + manager approval.

---

## P10E — Backup, restore, and rollback proof

**Objective:** Prove recoverability rather than merely documenting that backups should exist.

**Likely files:**

- Create: `scripts/ops/backup_postgres.py`
- Create: `scripts/ops/verify_postgres_restore.py`
- Create: `scripts/ops/object_storage_inventory.py`
- Create: `scripts/ops/release_preflight.py`
- Create: `docs/09-uygulama/14-phase10-pilot-backup-restore-runbook.md`
- Modify: `docs/07-operasyon/01-devops-ortamlar-surum-yonetimi.md`
- Modify: `docs/07-operasyon/04-runbook-operasyon-surecleri.md`

**PostgreSQL requirements:**

1. Create timestamped custom-format backup using environment-provided connection details.
2. Write a sidecar manifest containing no DSN/secret: source environment, release SHA, Alembic head, UTC time, size, SHA-256.
3. Refuse stdout dumps and unsafe world-readable permissions.
4. Restore into a newly created disposable database only.
5. Verify Alembic head, expected schema/model closure, tenant counts (aggregate only), critical RLS/FORCE RLS inventory, and app startup/readiness.
6. Destroy the disposable target after proof unless an explicit retain flag is supplied.
7. Never run destructive restore against staging/pilot/prod names.

**Object-storage requirements:**

- Inventory expected object keys/count/size/checksum metadata without logging document names or employee IDs.
- Verify source/backup namespace isolation.
- Use provider-native versioning/mirror tooling when configured; do not copy credentials into arguments/logs.
- Restore proof uses a disposable bucket/prefix and verifies a synthetic clean document only.
- Document consistency boundary: DB backup timestamp, object inventory timestamp, and accepted RPO gap.

**Rollback requirements:**

- Record previous immutable application SHA.
- Record migration compatibility decision.
- Application rollback must not automatically downgrade irreversible/data-changing migrations.
- Feature flags are the first rollback for newly enabled pilot surfaces where available.

**Focused gate:** one real staging backup, checksum read-back, disposable DB restore, app readiness on restored DB, one synthetic object restore, and cleanup proof.

---

## P10F — Active CI and release manifest

**Objective:** Replace local-only quality evidence with a reproducible repository gate while keeping deployment manual.

**Likely files:**

- Create: `.github/workflows/quality.yml`
- Optional create: `.github/dependabot.yml`
- Create: `scripts/release_manifest.py`
- Create: `docs/09-uygulama/15-phase10-release-candidate-checklist.md`
- Modify: `README.md`
- Modify: `docs/07-operasyon/03-test-stratejisi-qa.md`

**CI jobs:**

1. Backend static:
   - `uv lock --check`
   - Ruff
   - Python compile/import smoke
2. Backend focused tests:
   - existing default unit/API lane;
   - no production credentials;
   - no broad Phase 11 persona/E2E generation.
3. PostgreSQL migration/security lane:
   - disposable PostgreSQL 17 service;
   - cluster-global capability-role handling per existing tests;
   - migration head/drift and selected RLS checks.
4. Frontend:
   - deterministic install;
   - lint;
   - TypeScript;
   - production build;
   - high-severity dependency audit.
5. Security hygiene:
   - secret-pattern scan;
   - forbidden credential files;
   - no generated backup/runtime artifacts.
6. Contract/release:
   - OpenAPI generation/diff policy;
   - release manifest schema validation.

**Release manifest fields:**

- immutable commit SHA;
- application version;
- Alembic head;
- frontend build identifier;
- enabled service/worker names;
- artifact checksums where available;
- backup manifest reference;
- quality gate summary;
- creation timestamp.

No secrets, URLs with credentials, tenant/customer identities, or test passwords.

**Deployment:**

- No GitHub Actions auto-deploy.
- Branch protection is a repository-owner action: require quality workflow before merge once the first run is green.
- Review branch push and staging deployment still require supervisor verification; main merge/deploy requires Murat approval.

**Focused gate:** workflow syntax validation, one real review-branch workflow run if GitHub permissions allow, no-secret artifact inspection, release manifest generation and read-back.

---

## P10G — Pilot release candidate, staging acceptance, and Phase 11 handoff

**Objective:** Produce one immutable, recoverable, observable Phase 10 release candidate and hand it to Phase 11.

**Pre-deploy:**

1. Verify review branch remote SHA and clean tracked worktree.
2. Create fresh staging backup and checksum.
3. Verify migration head/drift; apply only additive migration if P10 created one.
4. Build frontend from review SHA.
5. Generate release manifest.
6. Capture existing backend/frontend/worker executable paths, CWDs, PIDs, and safe environment keys before stopping processes.

**Staging deployment:**

- Deploy the immutable review SHA, not uncommitted files.
- Start API, web, notification worker, and reporting worker from the same checkout SHA.
- Verify configured PostgreSQL, object storage, ClamAV, and worker dependencies before product smoke.
- Use synthetic/anonymized data only.
- Use a stable named Cloudflare tunnel/custom domain for pilot acceptance. If unavailable, label quick-tunnel verification as temporary staging only and do not call it durable pilot production.

**Narrow Phase 10 smoke:**

- local/public liveness and readiness;
- release SHA/version and DB head agree with manifest;
- tenant admin sees readiness checklist and remediation links;
- employee/manager cannot fetch or render admin readiness;
- second tenant is denied;
- login, employee home, leave request/approval, document metadata/upload guard, report/export start, privacy center basic route remain usable;
- PWA manifest/install and offline no-data behavior;
- backup manifest and disposable restore proof;
- workers remain healthy with no PII/noise regression;
- public auth guards remain `307/401` as contract requires.

**Explicitly deferred to Phase 11:**

- full backend regression and complete PostgreSQL marker lane;
- broad Playwright persona journeys;
- full role × scope × endpoint authorization matrix;
- all-table tenant isolation and BOLA matrix;
- concurrency/idempotency regression across prior phases;
- malformed frontend projection matrix;
- performance/load/query-plan campaign;
- final security review and demonstrated-defect repair loops.

**Checkpoint evidence:**

- starting and ending SHA;
- Codex-authored production commit(s) and Hermes-authored integration/fix commits clearly attributed;
- migration and schema counts if changed;
- exact focused commands and outputs;
- backup path, size, checksum, and restore result;
- release manifest path/checksum;
- staging process CWD/SHA;
- public/stable URL and endpoint statuses;
- remaining Phase 11 work and residual risks.

Do not merge to `main` or call the environment pilot production until Murat reviews this checkpoint and explicitly approves merge/deploy.

---

## 8. Codex production-generation contract

If implementation is delegated to Codex, use exactly:

```text
CLI: /opt/data/.npm-global/bin/codex
Model: gpt-5.6-sol
Reasoning effort: ultra
```

Required launch shape:

```bash
/opt/data/.npm-global/bin/codex exec \
  -m gpt-5.6-sol \
  -c 'model_reasoning_effort="ultra"'
```

Before launch:

1. Confirm live model catalog still supports `ultra`.
2. Build production-only transitive import closure.
3. Exclude tests, fixtures, credentials, `.env`, backup files, reports, old plans, runtime state, and staging data.
4. Pin starting SHA and no-merge/no-deploy boundary.
5. Tell Codex Phase 10 uses focused checks only; Phase 11 owns broad E2E/regression.
6. Prohibit arbitrary LOC limits, low-reasoning shortcuts, speculative frameworks, internal review fan-out, and fake production adapters.
7. Require production quality: architecture, security, performance, maintainability, bounded queries, usable UX.

Hermes owns:

- scope and policy decisions;
- diff integration;
- migration/RLS/authorization review;
- environment and credential boundaries;
- real PostgreSQL/storage/backup smoke;
- independent review;
- commit/push attribution;
- staging acceptance;
- main merge/deploy only after Murat approval.

---

## 9. Quality and acceptance gates

### Per-block focused gate

- changed backend Ruff/compile;
- changed frontend lint/typecheck;
- migration upgrade only when schema changes;
- one product happy path;
- 1–3 critical negative authorization/cache/data-leak assertions;
- diff/worktree/forbidden-artifact check.

Do not repeatedly run full backend, full PostgreSQL, broad OpenAPI, production build, or broad browser suites in every block.

### Phase 10 final gate

- Ruff;
- Python compile;
- `uv lock --check`;
- SQLite metadata compatibility;
- frontend lint;
- TypeScript;
- production build;
- high-severity dependency audit;
- clean PostgreSQL migration and drift check;
- downgrade/re-upgrade only if `0043` exists;
- focused readiness authorization/RLS smoke;
- PWA cache-security smoke;
- real backup + disposable restore proof;
- release manifest read-back;
- narrow integrated product smoke;
- secret/backup/runtime-artifact scan;
- clean tracked worktree and remote SHA equality;
- bounded independent review with all dispatched reviewers returned before completion.

### Phase 10 completion definition

Phase 10 is complete only when:

- all P10A–P10G Must items are delivered or explicitly removed by Murat;
- no demonstrated critical security/data-loss/cross-tenant defect remains;
- staging acceptance runs from one immutable pushed SHA;
- recovery proof exists;
- CI is active or a concrete GitHub-permission blocker is documented;
- stable pilot-domain decision is resolved or environment is explicitly labeled temporary staging;
- Phase 11 receives a frozen release candidate and deferred matrix.

---

## 10. Rollout and rollback

### Rollout

1. Review branch only.
2. Internal synthetic tenant.
3. Staging acceptance with focused smoke.
4. Murat review.
5. Fast-forward `main` only if gates remain green.
6. Deploy immutable main SHA.
7. Named tunnel/custom domain public verification.
8. Observation window: liveness/readiness, 5xx, auth failures, worker freshness, queue backlog, DB connections, backup freshness.
9. Pilot tenant enablement through existing feature flags.

### Rollback

- UI/readiness/PWA defect: disable surface/feature flag or deploy previous immutable SHA.
- Service defect: previous application SHA first when schema is backward-compatible.
- Migration defect: do not blindly downgrade; follow the specific migration compatibility plan and restore only from verified backup with explicit approval.
- PWA cache defect: publish new service-worker version that unregisters/clears only application-owned static caches; never delete unrelated browser storage.
- Worker defect: stop affected worker, preserve queued jobs, deploy previous SHA, verify lease/retry state.
- Backup/restore defect: Phase 10 cannot complete; do not proceed to pilot.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| “Pilot hardening” grows into enterprise infrastructure | Keep Must scope to readiness, safe observability, recovery, CI, PWA, release proof |
| Readiness projection leaks tenant HR data | Tenant-only permission, bounded booleans/counts, no platform visibility, cross-tenant denial |
| Service worker caches PII or stale auth | Static allowlist + network-only protected/API routes + explicit cache tests |
| Public readiness leaks topology | Generic public response; detailed reasons internal/redacted |
| Logs become a shadow audit/PII store | Allowlisted structured fields, no bodies/query/cookies/raw IDs, sample scan |
| Backup exists but cannot restore | Disposable real restore is a completion gate |
| Quick tunnel is mistaken for production | Stable named tunnel/domain required for pilot label |
| CI capability-role setup is flaky | Reuse existing PostgreSQL test-role patterns; keep cluster disposable |
| Support urgency creates privilege bypass | Default deny; tenant-admin action/screenshare; separate MFA/JIT design required |
| Phase 10 becomes a hidden full QA phase | Enforce narrow gates; Phase 11 owns exhaustive matrix and repair |
| Old migration history is edited | `0041`/`0042` immutable; additive `0043` only if required |

---

## 12. Open decisions required before relevant block

These do not prevent plan approval, but they must be resolved before the named implementation step:

1. **Stable pilot URL:** named Cloudflare tunnel/custom domain details before P10G pilot label.
2. **Pilot email:** real provider credentials out-of-band, or notifications explicitly disabled; fake adapter cannot be called production.
3. **Backup destination/encryption owner:** before P10E.
4. **Metrics backend:** none/internal Prometheus/Sentry or another approved service before optional P10C metrics export.
5. **Support model:** default no customer-data access; any JIT/break-glass request reopens the MFA/security design checkpoint.
6. **PWA icon/brand assets:** approve existing Wealthy Falcon HR identity or supply final assets before P10D polish.
7. **Pilot tenant data:** synthetic/anonymized for staging; real PII only after environment/legal/operational approval.

---

## 13. Recommended execution order and commits

1. `chore(release): establish phase 10 pilot readiness baseline`
2. `feat(setup): add tenant readiness workspace`
3. `feat(ops): add safe readiness and structured service signals`
4. `feat(pwa): add secure installable mobile shell`
5. `feat(ops): add verified backup and restore workflow`
6. `ci: activate phase 10 quality and release manifest gates`
7. `chore(release): prepare phase 10 pilot candidate`
8. Targeted post-review fix commits, with Hermes attribution, only when demonstrated findings require them.

Each commit must be coherent, production-only, and independently inspectable. Do not mix generated backups, temporary smoke scripts, credentials, runtime logs, Codex context capsules, or test reports into commits.

---

## 14. Final plan review checklist

- [x] Phase 10 is anchored to authoritative MVP/pilot documents.
- [x] Phase 9/main is a verified prerequisite, not assumed.
- [x] New HR/V1 modules are excluded.
- [x] Platform support discrepancy is resolved with safe default-deny behavior.
- [x] Backend, frontend, authorization, operations, CI, backup, rollout, and rollback are covered.
- [x] Migration history remains immutable.
- [x] Phase 10 narrow gates and Phase 11 exhaustive testing boundary are explicit.
- [x] Quick tunnel is not treated as durable pilot production.
- [x] Codex model/tool/effort and production isolation are pinned.
- [ ] Murat approves the Phase 10 direction.
- [ ] Murat explicitly authorizes implementation after plan review.
