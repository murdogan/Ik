# Wealthy Falcon HR — MVP First Release Master Development Plan

> **For Hermes/Codex:** Implement this plan phase-by-phase using 2–3 hour coherent feature blocks. The 20-minute supervisor interval is a progress and evidence check, not a task timebox. Do not start a later phase until the current phase gate is green and the review branch is pushed.

**Goal:** Deliver the first pilot-ready Wealthy Falcon HR release in which a company can be provisioned, users can securely authenticate with role/scope enforcement, HR can manage organization/employee/document data, employees can request leave, managers can approve it, reports/import/export work, and every critical operation is tenant-isolated, masked where necessary, and auditable.

**Architecture:** Evolve the existing FastAPI scaffold into a modular monolith instead of replacing it or introducing microservices. Use PostgreSQL as the operational datastore, Redis for cache/queue/rate limit, S3-compatible storage for documents/exports, and a Next.js responsive web/PWA surface. Keep module boundaries explicit, use application-owned transaction boundaries, and record critical audit events atomically in the same PostgreSQL database.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16+, Redis, an MVP worker selected by a short Phase-0 spike, S3/MinIO, Next.js + TypeScript, pytest, Playwright, Ruff, OpenAPI contract tests, k6.

---

## 1. Plan Authority and Scope

This is the implementation master plan for the **first live/pilot release (MVP)** described by:

- `docs/02-urun/03-mvp-v1-v2-kapsam-kararlari.md`
- `docs/08-yurutme/01-roadmap-fazlar-milestone.md`
- `docs/02-urun/02-kanallar-web-mobil-self-servis.md`
- `docs/03-moduller/01-core-auth-rbac.md`
- `docs/03-moduller/02-personel-ozluk-dokuman.md`
- `docs/03-moduller/03-izin-devamsizlik-onay.md`
- `docs/03-moduller/09-organizasyon-kadro-pozisyon.md`
- `docs/03-moduller/10-self-servis-talep-duyuru.md`
- `docs/03-moduller/11-raporlama-people-analytics.md`

The earlier file `.hermes/plans/2026-07-10_111500-sprint-1-feature-expansion-plan.md` remains historical input but is **superseded as an execution plan**. Its Organization Core ideas are incorporated into Phase 3 here, after architecture, tenant, auth, RBAC, transaction, and audit foundations are safe.

### MVP includes

- CORE: tenant lifecycle, settings, feature flags.
- AUTH: activation, email/password login, refresh rotation, logout, password reset.
- RBAC: default roles, permissions, own/team/department/branch/tenant/platform scopes.
- AUDIT: immutable critical-event history with differentiated platform/tenant visibility.
- ORG: default legal entity, branches/locations, departments, positions/job titles, manager links, assignments, basic org chart.
- EMP: employee master data, Employee 360, employment/assignment data, status lifecycle, masking.
- DOC: document types, checklist, upload/download metadata, expiry, secure object storage.
- LEAVE: types, holiday calendar, policy, balances, requests, approval/rejection/cancellation, team calendar.
- SELF-SERVICE: employee home/profile/leave/documents/requests/announcements.
- MANAGER: approval queue, team list, team calendar.
- NOTIFICATIONS: in-app plus provider-abstracted email; retryable background delivery.
- REP/IMPORT/EXPORT: dashboard, employee/leave/missing-document reports, CSV/XLSX exports, employee CSV dry-run/commit.
- KVKK/SECURITY/OPS: notice acknowledgement, field classification/masking, retention metadata, observability, backup/rollback, release hardening.

### Explicitly outside MVP

- Native payroll calculation, SGK, bank integrations.
- Full PDKS device integration, advanced shift optimization, payroll engine.
- ATS/candidate portal/career site.
- Performance/OKR/360.
- LMS/career/succession.
- Advanced report builder/semantic analytics/predictive analytics.
- AI features.
- SAML/SCIM/SIEM and dedicated tenant infrastructure.
- Native mobile application.
- Matrix organization, reorg simulation, workforce planning.
- Full workflow designer and complex multi-level approval builder.

---

# 2. Current-Code Assessment

## 2.1 Verified baseline

The current repository was inspected read-only before this plan was written.

- Branch: `main`, synchronized with `origin/main` at inspection time.
- Current application surface: 14 generated OpenAPI operations plus `/openapi.json`.
- Application modules currently implemented: tenant/user persistence foundation, employee CRUD, leave-request transitions, manual leave-balance summaries, dashboard, seed, OpenAPI/smoke governance.
- Quality gate verified on 2026-07-10:
  - `uv run ruff check backend` → passed.
  - `uv run pytest -q` → `329 passed, 1 warning`.
  - `uv run python scripts/backend_api_smoke.py` → `BACKEND_SMOKE_OK`, 15 documented endpoints.
- Approximate codebase size:
  - backend Python: 69 files / 10,537 lines including tests.
  - application package: 37 files / 3,322 lines.
  - documentation: 54 Markdown files / 11,032 lines.
- No frontend implementation currently exists (`package.json`, `.ts`, `.tsx` absent).

## 2.2 What is already structurally good

- FastAPI app factory and dependency injection entry points exist.
- SQLAlchemy 2 async and Alembic are already used.
- Public identifiers are UUIDs.
- Existing tenant-owned tables carry `tenant_id`.
- Important lifecycle/date constraints and compound indexes exist.
- List endpoints are bounded.
- Error envelopes and OpenAPI metadata have regression tests.
- Cross-tenant negative behavior is tested at API/service level.
- Tests are extensive relative to application size.
- Existing code is small enough to restructure safely before module growth.

## 2.3 Blocking architecture gaps before large expansion

The code is a good scaffold, but it must not be expanded unchanged into a large HRMS.

### A-001 — Tenant identity is currently caller-controlled

`backend/app/api/dependencies.py` accepts `X-Tenant-Id` as the authoritative tenant source. This is acceptable only for the current local scaffold. Protected endpoints must derive tenant from authenticated session/JWT and validate host/subdomain consistency. A caller-provided tenant header must never authorize access.

### A-002 — Auth/RBAC/current-user enforcement does not exist

Current leave decisions accept `decided_by_user_id` from request payload and only check that the user belongs to the tenant. The server must derive actor identity from the session, verify permission/scope, and ignore/reject actor IDs supplied by clients.

### A-003 — Services own commits

`EmployeeService` and `LeaveRequestService` call `session.commit()` internally. This prevents an application command from composing domain writes, audit events, outbox events, and notifications in one atomic transaction. Transaction ownership must move to an application Unit of Work/command boundary; inner services/repositories use `flush()`.

### A-004 — Flat packages will become coupling hotspots

The current `app/api`, `app/services`, `app/models`, and `app/schemas` structure works for five models but will become a shared-directory monolith. New development must move incrementally toward explicit module packages and import-boundary tests; no big-bang rewrite.

### A-005 — Destructive employee deletion is unsafe for HR data

`DELETE /employees/{id}` currently hard-deletes and FKs can cascade to dependent records. HR/leave/document/audit history must use archive/status/retention semantics. Hard delete is only allowed for narrowly defined pre-production or legally approved anonymization workflows.

### A-006 — Race conditions remain

- Employee-number availability uses check-then-insert and does not centrally map database unique violations.
- Leave approve/reject/cancel reads status then commits without row lock or optimistic version check.
- Idempotency keys do not exist for critical POST/decision operations.

These must be resolved before real users and parallel requests.

### A-007 — PostgreSQL-specific safety is not exercised in the primary suite

Most API/service/migration smoke tests run on SQLite. SQLite tests remain useful for speed, but they cannot prove PostgreSQL RLS, row locks, `citext`, JSONB, partial indexes, constraint behavior, pool behavior, or future partitioning. CI needs a real PostgreSQL integration lane.

### A-008 — Database runtime controls are minimal

`backend/app/db/session.py` enables `pool_pre_ping` but has no explicit pool size/overflow/recycle/acquisition timeout, statement timeout, transaction timeout, RLS context setup, or engine lifecycle disposal. These become mandatory before pilot load.

### A-009 — Query strategy will degrade with volume

- Offset pagination becomes expensive on deep pages.
- `lower(trim(department))` and `lower(...).contains()` can bypass ordinary indexes.
- Dashboard performs multiple sequential aggregate queries per request.
- Dashboard recent activity is reconstructed from current tables rather than the audit stream.
- Employee search has no explicit PostgreSQL `citext`/trigram/full-text plan.

### A-010 — Cross-cutting platform capabilities are missing

Correlation/request IDs, structured logging, centralized authorization, field masking, idempotency, outbox/events, background jobs, object storage, rate limiting, observability, and response metadata need foundation-level interfaces before modules duplicate them.

### A-011 — Tenant bütünlüğü ilişkisel veritabanında tam garanti edilmiyor

Mevcut child kayıtlar `tenant_id` taşıyor ancak bazı foreign key’ler yalnız global `id` kolonuna bağlanıyor. Örneğin bir `leave_requests` satırı teorik olarak `tenant_id=A` iken Tenant B’ye ait `employee_id` veya `user_id` taşıyabilir. Normal API servis kontrolleri bunu azaltır; fakat import, seed, bakım scripti, yeni servis veya doğrudan DB yolu bu kontrolü atlayabilir.

Büyük proje standardı:

- tenant-owned parent tablolarda gerektiğinde `(tenant_id, id)` unique/primary candidate key;
- tenant-owned child ilişkilerinde `(tenant_id, foreign_id)` composite foreign key;
- RLS, uygulama guard’ı ve composite FK birbirinin alternatifi değil, katmanlı savunmadır;
- mevcut ilişkiler expand-contract migration ve veri bütünlüğü taramasıyla dönüştürülür.

## 2.4 Architecture verdict

> **Verdict:** The current code is a clean, heavily tested scaffold and should be preserved as behavior, but its package boundaries, transaction ownership, tenant trust model, concurrency controls, and PostgreSQL test strategy are not yet suitable for direct large-project expansion.

The correct path is an **incremental modular-monolith refactor**, not a rewrite and not microservices.

---

# 3. Target Architecture and SOLID Rules

## 3.1 Target package direction

Target structure, introduced incrementally:

```text
backend/app/
  platform/
    config/
    db/
    tenancy/
    identity/
    authorization/
    audit/
    events/
    errors/
    observability/
    storage/
    workers/
  modules/
    core/
    organization/
    employees/
    documents/
    leave/
    self_service/
    notifications/
    reporting/
  api/
    app_factory.py
    middleware.py
    router_registry.py
```

Each domain module may contain:

```text
module/
  domain/          pure rules, value objects, transitions
  application/     commands, queries, ports, DTOs
  infrastructure/  SQLAlchemy repositories, provider adapters
  presentation/    FastAPI routes/schemas/dependencies
```

This is a direction, not permission for a single massive file move. Existing employee/leave endpoints remain behavior-compatible while their internals migrate one module at a time.

## 3.2 SOLID interpretation for this project

- **Single Responsibility:** routes translate HTTP; application handlers orchestrate; domain policies decide; repositories/query services persist/read; provider adapters call external systems.
- **Open/Closed:** notification, storage, export, clock, ID generation, audit and worker providers are ports with replaceable implementations.
- **Liskov:** fake/in-memory adapters must obey the same contracts as PostgreSQL/S3/email adapters.
- **Interface Segregation:** use small capability ports such as `AuditRecorder`, `EmployeeReader`, `ObjectStorage`, not one giant platform interface.
- **Dependency Inversion:** domain/application code does not import FastAPI, concrete email/S3 clients, or global settings.

Avoid ceremonial overengineering:

- Do not create a generic repository that merely mirrors every SQLAlchemy method.
- Use module-specific command repositories and optimized query services.
- Keep SQLAlchemy models if useful, but put business policies in testable pure functions/services.
- Use lightweight command/query separation, not distributed CQRS/event sourcing.

## 3.3 Transaction rule

Application command handlers own transactions:

```text
API route
  → authenticated RequestContext
  → permission check
  → application command
      → domain write(s)
      → audit event
      → outbox event when needed
  → one UnitOfWork commit
```

Critical domain write and audit write succeed or fail together. Notification delivery happens after commit through outbox/worker.

## 3.4 Tenant rule

- Login/public discovery: tenant from subdomain/custom domain/institution code.
- Protected requests: tenant from authenticated session/JWT.
- Host tenant and token tenant must match.
- Request body/header tenant IDs never grant authorization.
- Transaction start sets `SET LOCAL app.tenant_id` for PostgreSQL RLS.
- App role has no `BYPASSRLS`.
- Every background task carries signed/validated tenant context and fails closed without it.

## 3.5 Performance design target

MVP product target is 50–1,000 employee pilots, but implementation must remain healthy for a synthetic tenant with at least 10,000 employees and realistic dependent data.

Budgets before pilot release:

- Login p95 < 500 ms under agreed local/staging test profile.
- Employee list p95 < 300 ms for indexed common filters.
- Leave decision p95 < 800 ms under concurrent requests.
- Standard dashboard p95 < 1 s without cold export work.
- Large report/export runs asynchronously; API acceptance < 1 s.
- No unbounded list endpoint.
- No per-row N+1 query in list/Employee 360/report paths.
- No worker task without timeout, retry limit, idempotency and tenant concurrency control.

---

# 4. Audit Architecture and Visibility Model

## 4.1 Storage decision

Audit stays in the **same PostgreSQL database** for MVP.

- One append-only `audit_events` write store.
- Same transaction as critical domain changes.
- No public create/update/delete audit endpoints.
- Application DB role can insert and authorized query; normal runtime cannot update/delete.
- Retention/partition/archive are future-compatible but separate DB/SIEM is not required for MVP.

## 4.2 Required audit fields

- `id`, `occurred_at`.
- `scope_type`: `platform` or `tenant`.
- `tenant_id`: required for tenant events; null only for truly platform-global events.
- `actor_type`: `user`, `system`, `worker`, `platform_admin`, `support_session`.
- `actor_user_id`, `impersonator_user_id` where relevant.
- `event_type`, `category`, `severity`.
- `resource_type`, `resource_id`.
- `action`, `result`.
- `request_id`, `trace_id`, `session_id`.
- `ip_address`, safely bounded/redacted `user_agent`.
- `reason`, `support_ticket_id` where required.
- allowlisted/redacted `changed_fields`, `before_data`, `after_data`, `metadata` JSONB.
- `data_classification` and `visibility_class`.
- optional tamper-evidence/hash fields reserved without pretending to provide full cryptographic immutability in MVP.

Check constraint:

- `scope_type='tenant'` requires non-null `tenant_id`.
- `scope_type='platform'` cannot carry tenant business payload unless it is a break-glass/support event with explicit target metadata.

## 4.3 Visibility classes

- `platform_ops`: tenant lifecycle, plan, service health, feature rollout; no HR payload.
- `tenant_admin`: tenant configuration, users, roles, exports and broad business administration.
- `tenant_security`: auth/session/security/cross-access-denied events.
- `hr_operations`: employee/document/leave/organization events, redacted by field policy.
- `auditor_readonly`: compliance-safe view of authorized tenant history.
- `resource_timeline`: limited business-readable history for one employee/request/document.
- `subject_own`: user-visible history of the employee's own actions/status changes.
- `restricted`: special-category/security incidents requiring extra permission/step-up.

## 4.4 Role visibility matrix

| Role | Default audit visibility | Explicit exclusions |
|---|---|---|
| `super_admin` | Platform tenant lifecycle, plan/limit/feature operations, platform security/health | No tenant HR/document/leave payload by default |
| `tenant_admin` | Own tenant configuration, users/roles, exports, permitted business summaries | No raw secrets, tokens, passwords, document content; special-category payload redacted |
| `hr_director` | Own tenant HR/ORG/EMP/DOC/LEAVE/REPORT events | No platform ops; no auth attack details unless separately permitted |
| `hr_specialist` | Assigned tenant/branch/department HR operations | No unrelated department/branch, no unrestricted sensitive before/after |
| `auditor` | Broad read-only tenant audit according to audit permission and retention | No mutation; downloads/export require separate permission and audit |
| `it_admin` | Tenant auth/session/security/integration/config events | No employee document/medical/payroll/HR narrative payload |
| `manager` | No general audit center; limited team/resource timeline | No tenant-wide logs or sensitive field history |
| `employee` | Own action/status timeline only | No technical audit, actor details of protected internal decisions beyond product-safe reason |

## 4.5 Platform support / break-glass

A platform `super_admin` cannot simply switch to a customer tenant.

Minimum support-access design:

- `support_access_requests/grants` records target tenant, reason, ticket, requested scope, start/end, requester and tenant approver/pre-approved emergency policy.
- MFA/step-up required.
- Access is time-limited and automatically revoked.
- Every data read/write during support access carries `support_session_id`.
- `break_glass.started`, every restricted action, and `break_glass.ended` are visible in both platform and tenant-safe audit views.
- Tenant business payload remains minimized/redacted in the platform view.
- Emergency path without live customer approval requires a documented policy and creates immediate customer/security notification.

Break-glass read/write capability is not required for the first coding block. The data model and deny-by-default rule are established in Phase 2; full support flow is completed in Phase 9 before release.

## 4.6 Audit performance/retention

Initial indexes:

- `(tenant_id, occurred_at desc)`.
- `(tenant_id, event_type, occurred_at desc)`.
- `(tenant_id, resource_type, resource_id, occurred_at desc)`.
- `(actor_user_id, occurred_at desc)`.
- unique/request lookup where justified.

Rules:

- Cursor pagination only; no deep offset pagination.
- Never audit every harmless GET request.
- Audit every critical write and only sensitive/privileged reads.
- Store changed allowlisted fields, not full entity snapshots by default.
- Passwords, hashes, tokens, OTPs, secrets, document bodies, complete TCKN/IBAN and unnecessary health data are forbidden.
- Prepare monthly partitioning only after measured volume or before thresholds agreed in Phase 10; do not prematurely partition a tiny table.

---

# 5. Cross-Phase Quality Gates

Every Codex implementation block must end with evidence, not a “cron OK” status.

Required block evidence:

- coherent commit(s) on review branch;
- clean `git status` except declared generated artifacts;
- targeted tests for the changed behavior;
- Ruff and relevant type/static checks;
- PostgreSQL integration test when persistence/RLS/locking/index behavior changes;
- API/OpenAPI diff when routes change;
- smoke scenario executing new endpoint behavior;
- permission/scope matrix update when authorization changes;
- audit event test when critical behavior changes;
- docs/implementation-status update;
- pushed review branch.

Global gates after the project foundation phase:

```bash
uv run ruff check backend
uv run pytest
uv run python scripts/backend_api_smoke.py
```

They will be expanded with:

- PostgreSQL integration suite.
- import-boundary check.
- migration upgrade/drift test on PostgreSQL.
- frontend lint/typecheck/unit tests.
- Playwright critical-flow subset.
- security/dependency/secret scan.

A later phase cannot begin while:

- tests are red;
- migration head/drift is invalid;
- review branch is not pushed;
- tenant/authz negative tests fail;
- a known P1/P2 defect remains unresolved;
- current phase acceptance criteria are not recorded.

---

# PHASE 0 — Baseline, Architecture Stabilization and ADR Closure

**Purpose:** Preserve current behavior while changing the foundation so future modules do not multiply security, performance and coupling problems.

**Estimated Codex blocks:** 4–6 blocks, each 2–3 hours.

## 0.1 Baseline and characterization

- Freeze current OpenAPI and smoke behavior with contract snapshots.
- Preserve current employee/leave/dashboard behavior while refactoring.
- Add two test classes: fast SQLite tests and real PostgreSQL integration tests.
- Create deterministic PostgreSQL test database setup through Docker/CI service.
- Run Alembic upgrade/drift/constraint tests against PostgreSQL, not only SQLite.
- Record baseline query counts and response timing for current main endpoints.

## 0.2 Incremental modular-monolith skeleton

- Introduce `platform/` and `modules/` boundaries without moving every file at once.
- Move one existing module at a time with compatibility imports where necessary.
- Add import-boundary tests/rules:
  - presentation may depend on application;
  - application may depend on domain/ports;
  - infrastructure implements ports;
  - domain cannot import FastAPI/SQLAlchemy/settings/provider clients;
  - modules do not write another module's tables directly.
- Split the current large shared `api/errors.py` into platform error contract plus module error mapping incrementally.

## 0.3 Transaction and Unit of Work

- Add a small `UnitOfWork` abstraction around `AsyncSession`.
- Move `commit/rollback` out of employee/leave services.
- Make command handlers own commit.
- Add rollback tests proving domain write + audit/outbox can be atomic.
- Keep read query services optimized and SQLAlchemy-aware; do not force generic repositories.

## 0.4 Database runtime hardening

- Make engine creation part of app lifespan and dispose cleanly.
- Add environment-specific pool size, max overflow, pool timeout, recycle, connect/statement/transaction timeout settings.
- Add request/transaction correlation and SQL slow-query logging without PII.
- Decide and document PostgreSQL `citext`/normalized email strategy and employee search index strategy.
- Add connection-leak/rollback-after-error tests.
- Audit all tenant-owned relationships for DB-level tenant consistency.
- Introduce `(tenant_id, id)` candidate keys and `(tenant_id, foreign_id)` composite foreign keys where child and parent are tenant-owned.
- Convert current employee/user/leave-balance/leave-request relations with expand-contract migrations, pre-migration orphan/cross-tenant scans and rollback-safe verification.
- Add negative PostgreSQL tests proving cross-tenant foreign-key combinations fail even when application services are bypassed.

## 0.5 Concurrency/idempotency corrections

- Catch/map database unique violations instead of trusting only pre-check queries.
- Add optimistic version or row locks for leave decisions.
- Add idempotency foundation for critical POST/decision commands.
- Replace unsafe hard employee delete with compatibility-deprecation plan for archive/status behavior.

## 0.6 Worker selection spike

Compare the simplest production-safe Redis-backed worker options against:

- Python 3.13 support;
- retries/timeouts/DLQ behavior;
- tenant concurrency limits;
- async compatibility;
- observability;
- operational simplicity.

Record one ADR and implement only the common port/fake in Phase 0; provider setup comes in later phases.

**Likely files affected:**

- `backend/app/main.py`
- `backend/app/db/session.py`
- `backend/app/api/dependencies.py`
- `backend/app/services/*` incrementally
- new `backend/app/platform/*`
- new `backend/app/modules/*`
- `backend/tests/*`
- `.github/workflows/*` or active CI workflow
- Alembic test/config files

**Phase-0 gate:**

- Existing OpenAPI operations remain compatible or approved migration notes exist.
- Current 329 tests remain green or are intentionally superseded with equivalent coverage.
- PostgreSQL migration/integration lane is green.
- No application service owns `commit()`.
- Import-boundary test is active.
- Concurrent leave decision test proves exactly one terminal decision wins.
- Duplicate employee race maps to deterministic conflict response.
- Tenant-owned composite FK negative tests prove a child row cannot reference another tenant’s employee/user/resource even through direct DB writes.
- No new product module starts before this gate.

---

# PHASE 1 — Platform Core, Tenant Context and API Standards

**Purpose:** Build trustworthy request/tenant/config foundations before authentication and business modules expand.

**Estimated Codex blocks:** 3–5.

## 1.1 Tenant lifecycle and settings

- Complete tenant model and APIs for platform-controlled provisioning, status, locale/timezone, plan and internal feature flags.
- Create tenant settings with typed/validated keys; avoid arbitrary unsafe settings payloads.
- Seed one default legal entity placeholder only after Organization phase migration is ready.
- Define suspended/offboarding/closed behavior.

## 1.2 Request context

- Add immutable `RequestContext` containing request/trace ID, tenant, actor/session, auth strength and support-session metadata.
- Correlation middleware creates/propagates request and trace identifiers.
- Standardize errors and `{data, meta}`/pagination response contracts with a compatibility plan.
- Tenant header remains only for explicitly internal/dev compatibility paths; it cannot authorize protected domain access after Phase 2.

## 1.3 RLS foundation

- Add RLS migration helpers and catalog tests for every tenant-owned table.
- App transaction sets `SET LOCAL app.tenant_id`.
- App DB role cannot bypass RLS.
- Admin/platform operational queries use separate narrowly scoped paths/roles, never accidental normal-session bypass.
- Add direct DB-level cross-tenant negative tests.

## 1.4 Platform operations surface

- Platform tenant list/provision/status endpoints are separate from tenant business endpoints.
- Platform role sees tenant metadata/health/plan/limits, not customer HR records.
- Feature flags support safe module rollout without per-customer code forks.

**Audit events:** `tenant.created`, `tenant.status_changed`, `tenant.setting_changed`, `feature_flag.changed`.

**Phase-1 gate:**

- Tenant context is immutable and RLS-protected in PostgreSQL.
- Tenant A cannot read/write Tenant B through API, repository, raw DB session, cache key helper or background-task fake.
- Platform endpoints expose no HR data.
- Correlation IDs appear in error/log/audit test fixtures without PII.

---

# PHASE 2 — Authentication, Sessions, RBAC and Audit Foundation

**Purpose:** Replace caller-supplied identity/tenant behavior with secure authenticated context and establish audit as a cross-cutting platform capability.

**Estimated Codex blocks:** 6–9.

## 2.1 Identity and activation

- User invitation and activation tokens stored hashed and expiring.
- Tenant-aware email/password login.
- Argon2id or approved equivalent.
- Password reset with one-time hashed token.
- Lockout/rate-limit behavior by IP + tenant + identity.
- Admin/platform roles MFA-ready; platform super admin must use step-up before privileged operations.

## 2.2 Session model

- Short-lived access token.
- Server-side refresh session/family.
- Refresh rotation and reuse detection.
- Logout/revoke.
- Permission version/session invalidation on role changes.
- Web storage decision: HttpOnly secure refresh cookie/BFF-compatible flow; avoid durable browser localStorage tokens.

## 2.3 RBAC and scope

Seed/implement:

- platform: `super_admin`;
- tenant: `tenant_admin`, `hr_director`, `hr_specialist`, `it_admin`, `auditor`, `manager`, `employee`;
- future roles can exist but do not gain MVP module behavior automatically.

Permission format:

```text
<resource>:<action>:<scope>
<resource>:<action>:<field>
```

Implement reusable permission dependency/policy service and own/team/department/branch/tenant/platform scope primitives. Deny by default.

## 2.4 Current actor correction

- Protected API commands derive actor ID from session.
- Remove/ignore client-supplied `requested_by_user_id` and `decided_by_user_id` as authorization sources.
- Leave current endpoints remain backward-compatible only through an explicit deprecation period if needed.

## 2.5 Audit write model

- Add append-only `audit_events` migration/model/recorder.
- Write through injected `AuditRecorder` inside the command Unit of Work.
- Add safe metadata builder/redaction allowlist.
- Add DB grants/trigger or equivalent verified control preventing normal runtime update/delete.
- Add cursor query service and retention-ready indexes.

## 2.6 Audit read surfaces

Separate APIs/read policies:

- `/api/v1/platform/audit-events` — platform-only categories.
- `/api/v1/audit-events` — current tenant and permission-filtered.
- resource-safe timelines are exposed by their owning modules, not by leaking raw audit metadata.

Implement the role visibility matrix in Section 4 and test every role/category/tenant combination.

## 2.7 Web shell

Create Next.js TypeScript frontend foundation:

- login/activation/reset flows;
- route protection;
- role-aware shell/navigation;
- API client/error/correlation handling;
- responsive design tokens/components;
- platform operations shell separated from tenant application shell.

**Audit/security events:** auth success/failure, reset, invite, role changes, session revoke/reuse, denied cross-tenant, audit query/export, platform actions.

**Phase-2 gate:**

- Login → refresh rotation → logout E2E works.
- Refresh reuse revokes family.
- Protected endpoints reject tenant header without valid matching session.
- Role × scope × endpoint matrix is automated.
- Platform super admin cannot read tenant HR events by default.
- Tenant roles see only permitted audit categories/scopes.
- Audit cannot be updated/deleted through normal runtime role.
- Domain write and audit rollback together on forced failure.

---

# PHASE 3 — Organization Core and Manager Scope

**Purpose:** Establish the structure required by employee assignments, team permissions, leave approvals and headcount reporting.

**Estimated Codex blocks:** 5–7.

## 3.1 MVP organization model

- Default/single legal entity for simple tenants; model remains future-compatible.
- Branch/location with timezone and status.
- Department hierarchy with parent relation and cycle prevention.
- Position/job-title catalog without V1 budget/workforce-planning scope.
- Employee assignment relationship with department, position, branch and manager.
- Team scope derived from assignments, not free text.

## 3.2 APIs and screens

- Legal entity/settings read/update appropriate for MVP.
- Branch/location CRUD/archive.
- Department CRUD/archive/tree.
- Position/job-title CRUD/archive.
- Employee assignment create/change/read.
- Lazy/basic org chart and team list.
- Tenant admin/HR organization screens in Next.js.

## 3.3 Migration from current strings

Current `Employee.department` and `position` strings must not be abruptly removed.

Use expand-contract:

1. Add structured tables/FKs/assignment.
2. Backfill or map existing strings for demo data.
3. Dual-read or compatibility response during migration.
4. Move filters/dashboard to structured IDs.
5. Deprecate legacy strings only after API/frontend migration and verified data report.

## 3.4 Performance

- Index hierarchy/tenant/status/code/assignment manager fields.
- Org chart uses lazy children/page boundaries; no full tenant tree payload for large organizations.
- Team scope query is explicit and explain-analyzed on synthetic hierarchy.

**Audit events:** department/branch/position create/update/archive, assignment changed, reporting line changed.

**Phase-3 gate:**

- Department cycle is impossible.
- Archived records cannot be newly assigned but history remains readable.
- Manager can see only derived team scope.
- Structured organization replaces legacy string behavior without breaking existing employee API unexpectedly.
- Org chart avoids N+1 and meets agreed synthetic-load budget.

---

# PHASE 4 — Employee Master Data, Employee 360 and Field Security

**Purpose:** Turn the minimal employee row into the reliable master record used by all remaining MVP modules.

**Estimated Codex blocks:** 7–10.

## 4.1 Data separation

Build focused records rather than one unlimited employee table:

- employee identity/master record;
- personal profile;
- employment record;
- organization assignment;
- employee-user link;
- field classification metadata/policy;
- profile change requests.

Do not add payroll/health/performance fields simply because they may be useful later.

## 4.2 Employee lifecycle

- Create/update/archive/status transitions.
- No ordinary hard delete.
- Termination remains MVP-limited: date/reason/status and dependent-open-process checks; full offboarding is V1.
- Optimistic versioning for conflicting updates.
- Employee-number and email normalization/uniqueness strategy enforced at DB and API.

## 4.3 Employee 360

API and screen tabs:

- summary;
- personal information;
- employment information;
- organization assignment;
- documents summary;
- leave summary;
- requests;
- product-safe activity timeline.

## 4.4 Masking and own/team/HR views

- TCKN/passport/IBAN fields are not added until encryption key/provider strategy is implemented and tested.
- Sensitive values encrypted at application boundary; searchable fields use approved hash/blind-index strategy only when needed.
- Manager view excludes sensitive personal/financial/special-category data.
- Employee own view is mask/allow policy-driven.
- Sensitive unmask requires permission, reason/step-up as configured, and audit.

## 4.5 Frontend

- HR employee list with indexed filters and cursor pagination.
- Employee 360 detail/drawer/page.
- Employee self profile.
- Limited profile change request/HR decision flow.
- Role-aware empty/loading/error states.

**Audit events:** employee created/updated/status changed/assignment changed, sensitive field viewed, profile change requested/approved/rejected.

**Phase-4 gate:**

- HR creates/updates/archives employees.
- Employee number uniqueness remains race-safe.
- Own/team/tenant and field-level views are tested.
- Manager cannot access sensitive fields through API, export or frontend.
- Employee 360 does not use per-tab/per-row N+1 queries.
- Hard delete is unavailable to normal roles.

---

# PHASE 5 — Employee Documents and Özlük Checklist

**Purpose:** Deliver secure employee-file value without turning the MVP into a full DMS.

**Estimated Codex blocks:** 5–8.

## 5.1 Document domain

- Document types with required/optional rules, expiry behavior, allowed roles and sensitivity.
- Employee document metadata; object body remains in S3/MinIO.
- Required-document checklist and missing/expiring status.
- Archive/retention metadata rather than destructive deletion.

## 5.2 Storage and upload security

- Tenant-prefixed storage key.
- File size and extension allowlist.
- MIME + magic-byte validation.
- Malware-scan interface and quarantine status; local fake for development.
- Short-lived presigned upload/download URLs issued only after tenant/scope/document permission checks.
- Never store document contents in audit or application logs.

## 5.3 APIs and screens

- Document type management.
- Employee document list/upload/metadata/archive/download.
- Employee own permitted documents.
- Missing/expiring checklist.
- HR employee document tab and employee self-service document view.

## 5.4 Background jobs

- Malware-scan workflow.
- Expiry reminders.
- Checklist snapshot/refresh if measurement proves necessary.

**Audit events:** upload, scan result, metadata/visibility change, view/download, archive; storage URL issuance without storing secret URL.

**Phase-5 gate:**

- Cross-tenant object key/URL access fails.
- Unauthorized role cannot obtain presigned URL.
- Every sensitive view/download is audited.
- Invalid/dangerous upload is rejected or quarantined.
- Missing-document report data is correct.

---

# PHASE 6 — Leave Types, Policies, Balances and Approval Workflow

**Purpose:** Replace the current manual balance placeholder with the MVP leave workflow and manager-scope enforcement.

**Estimated Codex blocks:** 8–12.

## 6.1 Leave configuration

- Leave types: annual, excuse, unpaid, medical/report starter set.
- Simple MVP policy per tenant/type: paid flag, document requirement, negative balance default off, accrual/carryover settings kept intentionally limited.
- Holiday calendars and weekend/workweek configuration.
- Policy version/effective date to prevent retroactive silent changes.

## 6.2 Balance ledger/read model

- Replace manual summary as the source of truth with append-only balance transactions/adjustments or another explicitly justified ledger model.
- Derived balance read model: earned/adjusted/used/planned/available.
- Manual adjustment requires separate permission and reason.
- Rebuild/reconciliation test proves read model correctness.

## 6.3 Request calculation

- Calculate counted days using workweek and holiday calendar.
- Validate overlap, status, balance and required document rules.
- Derive requester from current employee/user link.
- Route approval to current manager assignment.

## 6.4 Concurrent decisions

- Row lock/optimistic version/idempotency ensure exactly one approve/reject/cancel transition wins.
- Decision actor comes from current session.
- Approval updates balance/timeline atomically with audit and outbox.
- Cancellation restores/reserves balance according to explicit state rules.

## 6.5 APIs and vertical UI

- Leave type/config admin.
- Employee own balances/history/request form.
- Manager approval queue with employee balance/team calendar context.
- Team calendar.
- HR leave list/manual adjustment.
- Mobile/PWA critical flows kept within documented interaction targets.

**Audit events:** requested, approved, rejected, cancelled, balance adjusted, policy changed.

**Phase-6 gate:**

- Employee request → manager approval → balance/timeline update works E2E.
- Holiday/weekend calculation tests pass.
- Manager cannot act outside team.
- Concurrent contradictory decisions yield one winner.
- Manual adjustment requires permission/reason and shows redacted before/after audit.
- Current placeholder behavior is removed only through documented migration/backfill.

---

# PHASE 7 — Self-Service, Manager Portal, Announcements and Notifications

**Purpose:** Make the product usable by employees/managers instead of remaining an HR-only API.

**Estimated Codex blocks:** 6–9.

## 7.1 Employee home

- Personal summary.
- Leave balance and quick request.
- Pending/recent request status.
- Document checklist/expiry summary.
- Targeted announcements.
- In-app notifications.

## 7.2 Manager portal

- Approval queue.
- Team list/basic employee work information.
- Team leave calendar.
- No payroll/TCKN/IBAN/health visibility.

## 7.3 Basic request model

MVP request types are fixed and limited:

- leave;
- profile change;
- document request.

Do not build a dynamic workflow designer. Provide one normalized user timeline and approval queue read model where useful while domain modules still own state transitions.

## 7.4 Announcements

- HR creates/publishes tenant announcement.
- Target by role/department/branch using tenant-safe rules.
- Optional acknowledgement for critical announcements.
- Employee list/detail/ack.

## 7.5 Notification infrastructure

- In-app notification persistence.
- Provider port for email; fake/local implementation and production adapter configuration without secrets in code.
- Outbox-based post-commit delivery.
- Worker retries/backoff/terminal failure/DLQ or failed-state handling.
- Idempotent delivery and notification log.
- Channel preference center remains V1 except essential opt-out/legal behavior.

**Audit events:** request/approval status, announcement publish/ack, notification configuration and delivery administration; do not flood audit with every ordinary delivery retry.

**Phase-7 gate:**

- Employee portal and manager portal critical paths work responsively.
- Targeted announcements never cross tenant/scope.
- Notification failure does not roll back committed business transaction.
- Retry does not duplicate user-visible notifications.
- Role-based navigation is backed by API authorization, not only hidden UI.

---

# PHASE 8 — Dashboard, Reports, Export and Employee Import

**Purpose:** Provide pilot onboarding and management output without building a full BI platform.

**Estimated Codex blocks:** 7–10.

## 8.1 Dashboard redesign

- HR dashboard: headcount, current/new/terminated workers, pending leave, missing/expiring documents.
- Manager dashboard/team metrics limited by team scope.
- Current multi-query dashboard is measured and consolidated/cached where beneficial.
- Recent activity reads product-safe audit-derived events rather than inferring all history from current tables.
- Cache keys tenant/role/scope-aware and invalidated by domain events or short safe TTL.

## 8.2 Reports

- Employee report.
- Leave report.
- Missing/expiring document report.
- Scope and field permissions applied before aggregation/export.
- No raw SQL/report builder.

## 8.3 Export jobs

- CSV and XLSX.
- Async export job with requested fields/filters/scope snapshot.
- Permission re-check at generation and download.
- S3/MinIO file with expiry and download limits if required.
- Row/file limits and cancellation/failure states.
- Export audit records row count and field classifications, not file contents.

## 8.4 Employee import

- Downloadable schema/versioned template.
- Upload → mapping validation → dry-run → row-level errors/warnings → explicit commit.
- Duplicate strategy and idempotent import key.
- Async processing for large input.
- No real PII in fixtures/staging.
- Import summary/audit; not every row copied into audit payload.

## 8.5 Performance

- Cursor pagination for employee/audit/high-volume lists.
- `EXPLAIN (ANALYZE, BUFFERS)` captured for common report/list queries against synthetic data.
- Export/import memory remains bounded/streamed/chunked.

**Audit events:** report/export requested/generated/downloaded/failed, import started/validated/committed/failed.

**Phase-8 gate:**

- 10k synthetic-employee common list/report queries meet agreed budgets or exceptions are documented.
- Imports produce deterministic row errors and atomic/controlled commit semantics.
- Exports cannot include unauthorized fields/rows.
- Dashboard query count and latency are measured and bounded.

---

# PHASE 9 — KVKK, Audit Visibility Hardening and Platform Support Access

**Purpose:** Complete privacy/accountability controls and prove platform/tenant audit separation before pilot.

**Estimated Codex blocks:** 5–8.

## 9.1 Privacy notice and acknowledgement

- Versioned privacy notice.
- Employee first-login/read acknowledgement proof: version/hash/time/IP/user agent where lawful/necessary.
- Consent only for purposes requiring consent; do not model every lawful HR processing activity as consent.
- Retention metadata per data/document category.

## 9.2 Field classification and masking completion

- Every personal/sensitive field has classification and policy.
- API serialization, frontend rendering, reports and exports use the same field policy service.
- Sensitive unmask/read requires permission and audit; step-up where configured.
- Logs/errors/audit metadata redaction tested.

## 9.3 Audit visibility matrix implementation review

- Automated tests for every role in Section 4.
- Tenant admin, HR, IT and auditor views are category/scope/redaction-specific.
- Manager/employee receive product timelines, not raw audit access.
- Audit export requires separate permission and is itself audited.

## 9.4 Break-glass/JIT support

- Platform super admin default deny for tenant business data.
- Support request/grant/session model.
- Reason, ticket, scope, tenant approval or documented emergency policy, expiry and automatic revoke.
- Tenant-visible start/action/end audit trail.
- Platform-visible operational trail without copying customer-sensitive payload.
- Step-up/MFA and alert/notification.

## 9.5 Retention and immutability

- Normal app role cannot mutate/delete audit.
- Retention job interfaces and legal-hold readiness.
- Decide partition threshold from measured event volume.
- Backup/restore includes audit and validates ordering/tenant integrity.

**Phase-9 gate:**

- Super admin cannot inspect tenant HR data without an active support grant.
- Tenant sees permitted break-glass activity.
- IT admin cannot read HR payload; HR cannot read restricted security payload by default.
- No forbidden secret/PII appears in logs/audit fixtures/scans.
- Audit update/delete attempts fail under runtime DB role.

---

# PHASE 10 — Observability, Performance, Security and Operational Hardening

**Purpose:** Prove the modular product is operable and will not fail immediately under pilot growth.

**Estimated Codex blocks:** 5–8.

## 10.1 Observability

- Structured logs with request/trace/tenant tags and PII redaction.
- Metrics: API latency/error, DB pool, slow queries, worker queue/retry/failure, storage/provider errors.
- Health/readiness/liveness separation.
- Alert thresholds and operator runbooks.

## 10.2 Database/performance

- Real PostgreSQL load dataset and query plans.
- Composite/partial/trigram indexes based on actual query patterns.
- Pool saturation and statement timeout tests.
- Dashboard cache behavior.
- Audit cursor query and retention-volume benchmark.
- Soak test for connection/session/memory leaks.

## 10.3 Security

- BOLA/role/scope matrix suite.
- SAST/SCA/secret scan/container scan.
- Upload security tests.
- Auth rate limit/lockout/token replay tests.
- CSRF/CSP/cookie/security-header checks for web.
- Staging DAST baseline.

## 10.4 Operations

- Backup/PITR configuration documentation and restore drill.
- Migration expand-contract and rollback rehearsal.
- Worker DLQ/failed-job replay runbook.
- Object-storage lifecycle/backup policy.
- Incident severity and response runbook linked to observable signals.

**Phase-10 gate:**

- No open critical/high security issue; P1/P2 release-blocking defects zero.
- Performance budgets met or explicit signed exceptions/mitigations exist.
- Restore test succeeds.
- Rollback/migration rehearsal succeeds.
- No connection/memory leak in soak profile.

---

# PHASE 11 — End-to-End Pilot Validation and First Release

**Purpose:** Validate product value and release safety with one realistic pilot tenant.

**Estimated Codex blocks:** 4–7 plus human UAT.

## 11.1 Pilot setup

- Provision pilot tenant and first tenant admin.
- Configure organization, roles, leave types/calendar, document types and announcements.
- Import realistic anonymized/synthetic employee data.
- Confirm feature flags and environment config.

## 11.2 Required E2E scenarios

1. Platform provisions tenant without seeing customer HR data.
2. Tenant admin activates account, invites users and assigns roles.
3. HR creates org structure and employee assignment.
4. HR creates employee and document checklist.
5. HR/employee uploads a permitted document; unauthorized user is denied.
6. Employee logs in, sees own profile/balance/documents and requests leave.
7. Correct manager sees context and approves/rejects.
8. Balance, calendar, notification and audit update correctly.
9. HR runs employee/leave/missing-document reports and authorized export.
10. Employee import dry-run identifies invalid rows and commits valid data safely.
11. Tenant admin/auditor/IT/HR audit views differ as designed.
12. Platform break-glass is denied without grant and fully traced with a grant.
13. Cross-tenant negative scenario is executed at API, DB/RLS, storage, worker and export layers.

## 11.3 Release evidence

- UAT pass rate ≥95%.
- No open P1/P2 defect.
- Full backend/frontend/contract/E2E/security gate reports.
- Migration and rollback evidence.
- Backup/restore evidence.
- Performance report.
- Data-import reconciliation report.
- User/admin training notes and support/runbook.
- Review branch merged only after explicit user approval.
- Staging/pilot deployment only after explicit user instruction.

**MVP complete definition:**

> A pilot company can operate employee master data, organization, employee documents and leave approval through role-appropriate web/self-service experiences, obtain basic reports/import/export, and prove tenant isolation, masking, audit accountability, operational recovery and acceptable performance.

---

# 6. Codex Execution Protocol

## 6.1 Work unit and model policy

- Codex model is `gpt-5.6-sol`.
- Reasoning effort is `ultra` for the complete MVP implementation. Architecture, security, tenant isolation and migration correctness take priority over speed/token economy.
- Do not silently lower effort after a retry or limit reset; resumed work must continue with `ultra` unless the user explicitly changes this decision.
- One Codex task is a coherent 2–3 hour feature block within the active phase.
- Do not split work into repetitive five-minute regression tasks unless repairing a failed gate.
- 20-minute supervisor checks inspect evidence and continuation needs; they do not terminate healthy work.

## 6.2 Prompt content for every block

Each Codex prompt must include:

- product/user outcome;
- active phase and dependency state;
- current architecture and reusable patterns;
- data model and migration constraints;
- auth/tenant/scope/field policy;
- audit events and redaction requirements;
- concurrency/idempotency requirements;
- performance/query budget;
- exact acceptance criteria;
- tests/smoke/OpenAPI/docs requirements;
- forbidden domains/side effects;
- instruction not to deploy/merge/change secrets.

## 6.3 Supervisor checks every 20 minutes

The supervisor must verify:

- process actually exists and log advances;
- active task/phase remains correct;
- files/commits show meaningful progress;
- no unrelated scope expansion;
- tests are not being deleted/weakened;
- secrets/config/deploy are untouched;
- token/usage limit is not blocking work;
- if blocked, record exact cause and schedule retry at the valid reset time;
- completed block has commit + gates + pushed review branch.

“Cron ran successfully” is not success. Success requires code/product evidence.

## 6.4 Limit exhaustion and automatic continuation

Limit/quota exhaustion is a pause, not a failed task and not a reason to advance the queue.

Supervisor requirements:

- Detect explicit Codex usage/rate/quota limit output separately from test failures, process crashes and product-code errors.
- Preserve the active task ID, base commit, prompt, branch, worktree and uncommitted changes.
- Keep the task `pending_limit`/retryable; never mark it `done`, `blocked`, or increment the red-gate failure counter solely because of quota exhaustion.
- Parse the provider reset timestamp from structured output or the log when available and store it as an absolute UTC/TR timestamp in supervisor state.
- If no reliable reset time is present, use a conservative recurring retry with exponential backoff capped at 30 minutes while retaining the normal 20-minute health check.
- Before the reset timestamp, health checks must not repeatedly launch Codex and waste requests.
- At reset time plus a small safety margin, a pre-created retry watchdog must invoke the same supervisor/task automatically. Cron-run sessions must not create recursive cron jobs; the watchdog is provisioned once when the coding run is started.
- Keep the ordinary 20-minute supervisor job as a safety net. If the exact-time retry is missed, the next supervisor tick resumes the same task.
- Resume with the same `gpt-5.6-sol` model and `ultra` effort; do not downgrade.
- On resume, inspect existing work and continue rather than restarting/overwriting the task blindly.
- Notify the user once when limit is detected with reset/retry time, and once when work actually resumes; stay silent on repetitive pre-reset checks.
- Success still requires commit + gates + review-branch push after continuation.

The coding automation is not considered ready to start until this behavior has deterministic parser/state tests for representative limit messages and a dry-run test proving the due-time watchdog resumes the same task only once.

## 6.5 Stop/review checkpoints

Stop automatically when:

- a phase gate is complete and the plan marks a human review point;
- architecture/security decision differs materially from this plan;
- migration would destroy or silently reinterpret data;
- tests are red and two focused repair attempts fail;
- credentials/production access are required;
- user says stop.

Do not autonomously merge to `main` or deploy.

---

# 7. Major Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Current flat architecture grows into coupling | Phase-0 incremental modular boundaries and import tests |
| Tenant header becomes auth vulnerability | Session-derived tenant + host match + PostgreSQL RLS |
| Audit cannot compose with writes | UoW-owned transaction and injected AuditRecorder |
| Super admin bypasses customer privacy | Default-deny platform role + JIT/break-glass grant + dual-visible audit |
| SQLite tests create false confidence | Dedicated PostgreSQL CI/integration lane |
| Employee hard delete destroys history | Archive/status/retention, no normal hard delete |
| Concurrent leave decisions conflict | Row lock/version + idempotency + concurrency tests |
| Dashboard/report load hurts API | Query consolidation, indexing, safe cache, async export |
| Audit table grows rapidly | Critical-event-only policy, cursor indexes, measured partition threshold |
| Documents leak through URLs | Tenant-prefixed object keys, short presigned URLs, scope checks, download audit |
| Frontend hides buttons but API allows access | Central API authorization and BOLA tests |
| Scope expands into payroll/ATS/AI | Explicit MVP exclusions and phase gate review |
| Overengineered DDD slows delivery | Lightweight modular monolith, focused ports, no generic repository ceremony |

---

# 8. Open Decisions to Confirm Before Relevant Coding Blocks

These do not block plan completion, but each must be decided before its implementation block:

1. Worker implementation selected after Phase-0 spike.
2. Production object-storage provider; MinIO remains local-compatible baseline.
3. MFA requirement: recommended mandatory for `super_admin`, optional/step-up-ready for tenant admin in MVP.
4. Email provider and sender domain; fake/local adapter used until credentials are supplied out-of-band.
5. First pilot leave types/calendar and carryover rules.
6. Sensitive-field encryption key provider/environment.
7. Emergency break-glass policy when tenant approver is unavailable.
8. Exact synthetic performance profile and staging infrastructure size.
9. Brand/product naming cleanup (`IK Platform` vs `Wealthy Falcon HR`) before public release.

Defaults in this plan are safe-deny and scope-minimizing; unresolved choices must not be guessed by Codex.

---

# 9. Faz Bazlı Beklenen MVP API Yüzeyi

Bu liste ürün sözleşmesi için başlangıç sınırıdır. Implementasyon sırasında mevcut endpoint uyumluluğu, REST tutarlılığı veya güvenlik gerekçesiyle isim değişikliği önerilebilir; değişiklik gerekçelendirilip OpenAPI diff ve migration/deprecation notuyla review edilmeden uygulanmaz.

## Faz 1 — Platform ve tenant

- `POST /api/v1/platform/tenants` — platform tarafından tenant oluşturma.
- `GET /api/v1/platform/tenants` — yalnız platform metadata listesi.
- `GET /api/v1/platform/tenants/{tenant_id}` — plan/durum/region/health metadata; HR verisi yok.
- `PATCH /api/v1/platform/tenants/{tenant_id}` — durum/plan/temel platform ayarları.
- `GET /api/v1/tenant` — oturumdaki tenant temel bilgisi.
- `GET /api/v1/tenant/settings` — yetkili tenant ayarları.
- `PATCH /api/v1/tenant/settings` — typed tenant ayar güncellemesi.
- `GET /api/v1/tenant/features` — etkin modüller/feature flags.

## Faz 2 — Auth, kullanıcı, rol ve audit

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/activate`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`
- `GET /api/v1/me`
- `POST /api/v1/users/invitations`
- `GET /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `PATCH /api/v1/users/{user_id}`
- `GET /api/v1/roles`
- `GET /api/v1/permissions`
- `PUT /api/v1/users/{user_id}/roles` — replace semantiği ve audit.
- `GET /api/v1/audit-events` — tenant/role/scope/redaction filtreli.
- `GET /api/v1/audit-events/{event_id}` — izin verilen güvenli detay.
- `GET /api/v1/platform/audit-events` — yalnız platform olayları.

## Faz 3 — Organizasyon

- `GET/POST /api/v1/legal-entities`
- `GET/PATCH /api/v1/legal-entities/{id}`
- `GET/POST /api/v1/branches`
- `GET/PATCH/DELETE /api/v1/branches/{id}` — DELETE semantiği archive/deactivate.
- `GET/POST /api/v1/departments`
- `GET/PATCH/DELETE /api/v1/departments/{id}` — hierarchy/cycle/archive kurallı.
- `GET /api/v1/departments/tree`
- `GET/POST /api/v1/positions`
- `GET/PATCH/DELETE /api/v1/positions/{id}` — archive semantiği.
- `GET /api/v1/org-chart` — lazy/root/parent parametreli.
- `GET/POST /api/v1/employee-assignments`
- `GET/PATCH /api/v1/employee-assignments/{id}`
- `GET /api/v1/teams/me` — yöneticinin türetilmiş ekip görünümü.

## Faz 4 — Employee master data

- Mevcut `GET/POST /api/v1/employees` güvenli şekilde evrilir.
- Mevcut `GET/PATCH /api/v1/employees/{employee_id}` korunur.
- Mevcut hard-delete endpoint archive/status semantiğine taşınır ve deprecation planı yayınlanır.
- `GET /api/v1/employees/{id}/profile`
- `PATCH /api/v1/employees/{id}/profile`
- `GET /api/v1/employees/{id}/employment`
- `PATCH /api/v1/employees/{id}/employment`
- `GET /api/v1/employees/{id}/summary` — Employee 360 aggregate/read model.
- `GET /api/v1/me/profile`
- `POST /api/v1/profile-change-requests`
- `GET /api/v1/profile-change-requests`
- `POST /api/v1/profile-change-requests/{id}/approve`
- `POST /api/v1/profile-change-requests/{id}/reject`
- `GET /api/v1/employees/{id}/activity` — raw audit değil, ürün-güvenli timeline.

## Faz 5 — Belgeler

- `GET/POST /api/v1/document-types`
- `GET/PATCH/DELETE /api/v1/document-types/{id}` — kullanımda ise archive.
- `GET /api/v1/employees/{id}/documents`
- `POST /api/v1/employees/{id}/documents/upload-intents`
- `POST /api/v1/employees/{id}/documents/{document_id}/complete-upload`
- `GET/PATCH /api/v1/employees/{id}/documents/{document_id}`
- `POST /api/v1/employees/{id}/documents/{document_id}/download-intents`
- `DELETE /api/v1/employees/{id}/documents/{document_id}` — archive/retention kontrollü.
- `GET /api/v1/employees/{id}/document-checklist`
- `GET /api/v1/me/documents`
- `POST /api/v1/me/documents/{document_id}/download-intents`

## Faz 6 — İzin

- `GET/POST /api/v1/leave-types`
- `GET/PATCH/DELETE /api/v1/leave-types/{id}` — deactivation ve history koruması.
- `GET/POST /api/v1/holiday-calendars`
- `GET/PATCH /api/v1/holiday-calendars/{id}`
- `GET/POST /api/v1/leave-policies`
- `GET/PATCH /api/v1/leave-policies/{id}` — version/effective-date kurallı.
- `GET /api/v1/me/leave-balances`
- Mevcut `GET /api/v1/employees/{id}/leave-balances` gerçek ledger/read modeline taşınır.
- `GET/POST /api/v1/leave-requests`
- `GET /api/v1/leave-requests/{id}`
- `POST /api/v1/leave-requests/{id}/approve`
- `POST /api/v1/leave-requests/{id}/reject`
- `POST /api/v1/leave-requests/{id}/cancel`
- `POST /api/v1/leave-adjustments`
- `GET /api/v1/team-calendar`
- `GET /api/v1/approval-tasks` — manager queue/read model.

## Faz 7 — Self-servis, duyuru ve bildirim

- `GET /api/v1/self-service/home`
- `GET /api/v1/requests`
- `GET /api/v1/requests/{id}`
- `GET/POST /api/v1/announcements`
- `GET/PATCH /api/v1/announcements/{id}`
- `POST /api/v1/announcements/{id}/publish`
- `POST /api/v1/announcements/{id}/ack`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/read-all`

## Faz 8 — Rapor, export ve import

- Dashboard endpointi rol/scope bazlı yeni sözleşmeye evrilir.
- `GET /api/v1/reports/employees`
- `GET /api/v1/reports/leaves`
- `GET /api/v1/reports/documents/missing`
- `POST /api/v1/export-jobs`
- `GET /api/v1/export-jobs/{id}`
- `POST /api/v1/export-jobs/{id}/download-intents`
- `GET /api/v1/employees/imports/template`
- `POST /api/v1/employees/imports`
- `GET /api/v1/employees/imports/{id}`
- `POST /api/v1/employees/imports/{id}/commit`

## Faz 9 — Privacy ve platform support

- `GET /api/v1/privacy/notices/active`
- `GET/POST /api/v1/privacy/notices` — yetkili tenant yönetimi.
- `POST /api/v1/privacy/notices/{id}/publish`
- `POST /api/v1/privacy/notices/{id}/acknowledge`
- `GET /api/v1/privacy/acknowledgements` — izinli read-only görünüm.
- `POST /api/v1/platform/support-access-requests`
- `GET /api/v1/platform/support-access-requests`
- `POST /api/v1/support-access-requests/{id}/approve` — tenant yetkilisi.
- `POST /api/v1/platform/support-access-requests/{id}/start`
- `POST /api/v1/platform/support-sessions/{id}/end`

Tüm list endpointleri başlangıçta bounded, yüksek hacimli alanlarda cursor tabanlı ve `{data, meta}` sözleşmeli olacaktır. Her protected endpoint permission metadata taşır. Actor ve tenant kimliği request payload'ından alınmaz.

---

# 10. Final Planning Checklist

- [x] First-release boundary identified from repository documents.
- [x] Current implementation verified with real quality gates.
- [x] Large-project/SOLID gaps identified before feature expansion.
- [x] Performance/data-layer risks assigned to explicit phases.
- [x] Same-database audit decision retained.
- [x] Platform super-admin and tenant audit visibility separated.
- [x] Break-glass/JIT support model defined.
- [x] Phase dependencies and acceptance gates defined.
- [x] Backend, frontend, audit, authorization, tests and operations included in every relevant vertical slice.
- [x] MVP exclusions preserved.
- [x] Codex 2–3 hour block and 20-minute supervisor protocol defined.
- [ ] User reviews and approves this plan direction.
- [ ] Explicit user approval is received before Codex implementation begins.
