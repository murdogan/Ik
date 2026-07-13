# Phase 4 — Employee Master Data, Employee 360 and Field Security

> **Execution:** Implement as product-first vertical blocks. Each block must produce manually testable backend + frontend behavior and a coherent commit. Do not advance after a red gate.

## Goal

Turn the existing minimal employee record and Phase 3 assignment foundation into a reliable employee master product: HR can create, find, inspect, update and archive employees; employees can view a policy-controlled self profile; managers see only safe team fields; sensitive field access is enforced by the API and audited.

## Current checkpoint

- Base: `origin/main` at `593633ec028c0fb7be13a7254b1ed942d4d254d1`.
- Phase 3 identity and organization are complete and deployed to public staging.
- Structured assignments already link employee → legal entity/branch/department/position/manager.
- Existing employee APIs and legacy department/position compatibility must remain functional through expand-contract migration.
- Stack: FastAPI, SQLAlchemy/Alembic, PostgreSQL RLS, Next.js/TypeScript, Playwright.

## Product-first rules

1. Persistence/migration → API/service → usable Next.js screen → manual demo recipe → focused risk-based checks.
2. Early blocks do not repeat full regression, all OpenAPI snapshots and every role permutation. Full hardening belongs to P4H.
3. Preserve tenant isolation, deny-by-default authorization, audit immutability, session boundaries and archive/history safety in every block.
4. Use strict RED → GREEN → REFACTOR for new behavior.
5. A block cannot complete with only tests, docs, migrations or refactoring.
6. Prefer existing platform patterns and small focused records over one unlimited employee table.
7. Keep one coherent commit per block, message containing its block ID.

## Deliberate exclusions

- No real email/SMTP/provider implementation; notification mail remains Phase 7.
- No TCKN, passport, IBAN, health/special-category, payroll, compensation or performance fields before encryption/key-provider design.
- No full offboarding workflow; termination remains date/reason/status plus dependent-process checks.
- No document upload/DMS (Phase 5), leave policy/workflow (Phase 6), notification center (Phase 7), import/export/reporting (Phase 8).
- No hard delete for normal product roles.
- No dynamic custom-field builder.

---

## P4A — HR employee directory and create flow

**Visible outcome:** An authorized HR user opens `/employees`, filters a cursor-paginated employee directory, creates a minimal employee, and opens the resulting employee summary. Navigation exposes “Çalışanlar” only with employee tenant-read permission.

**Scope:**
- Inspect and reuse current employee model/service/API contracts; add only the minimal expand fields/versioning required for a reliable list/create entry point.
- Normalize and enforce tenant-scoped employee number and email uniqueness at DB/API boundaries.
- Provide bounded indexed filters for status, query, legal entity, branch, department and position where current structured assignments permit.
- Build the Next.js employee directory, create dialog/page, empty/loading/error states and summary route/drawer.
- Preserve existing API compatibility and assignment history.
- Audit employee creation without sensitive values.

**Focused gates:** relevant migration/model/service/API tests; employee list/create smoke; frontend lint/typecheck; one Playwright HR create-and-open journey; Ruff changed backend.

## P4B — Personal and employment profile split + Employee 360 shell

**Visible outcome:** HR opens an employee 360 page with Summary, Personal, Employment and Organization tabs and can update approved MVP fields.

**Scope:** focused personal/employment records, optimistic version contract, effective field ownership, no sensitive identifiers; organization tab consumes Phase 3 assignment history rather than duplicating it.

**Focused gates:** update conflict behavior, tenant isolation, audit before/after allowlist, one Employee 360 browser journey.

## P4C — Employee-user link and self profile

**Visible outcome:** An employee account linked to an employee record opens “Profilim” and sees only its own allowlisted profile; HR can manage the link safely.

**Scope:** race-safe tenant employee↔membership/user link, own-scope API, inactive/mismatched identity behavior, role-aware navigation and self-profile UI.

**Focused gates:** cross-user and cross-tenant denial, link uniqueness/concurrency, self-profile browser journey.

## P4D — Field classification, masking and manager-safe team views

**Visible outcome:** HR, manager and employee receive different field projections from the same employee without relying on frontend hiding.

**Scope:** centralized field classification/projection policy; manager-safe team fields; own-view masking; tenant HR projection; sensitive unmask contract remains disabled until encryption/step-up exists.

**Focused gates:** API projection matrix for distinct security boundaries, direct endpoint bypass denial, frontend rendering checks, no sensitive values in audit/logs.

## P4E — Profile change requests

**Visible outcome:** Employee requests a permitted profile change; HR approves or rejects it; status and product-safe timeline update atomically.

**Scope:** fixed allowlist of changeable fields, request state machine, optimistic/idempotent decision, own/HR APIs, employee request and HR queue UI, audit events.

**Focused gates:** contradictory decision one-winner behavior, unauthorized field rejection, own/tenant isolation, E2E request→decision flow.

## P4F — Lifecycle, archive and limited termination

**Visible outcome:** HR changes lifecycle status, records a limited termination, or archives an employee while history and assignments remain readable.

**Scope:** explicit transitions, end date/reason, dependent open-process checks that exist in MVP, no hard delete, terminal/archive rules, version conflicts and audit.

**Focused gates:** invalid transition rejection, concurrent update behavior, retained history, normal-role DELETE absence, HR lifecycle browser journey.

## P4G — Employee 360 summaries and activity timeline

**Visible outcome:** Employee 360 presents bounded document/leave/request placeholders or current summaries and a product-safe activity timeline without N+1 behavior.

**Scope:** compose existing current data only; no Phase 5/6 domain expansion; bounded queries and role-safe timeline; polished empty/loading/error states.

**Focused gates:** query count/budget evidence, safe timeline redaction, role-aware screen journey.

## P4H — PostgreSQL/security/performance/final product gate

**Visible outcome:** The complete Phase 4 employee product is manually testable by tenant admin/HR/manager/employee test personas and ready for review branch handoff.

**Scope:** migration/backfill report, real PostgreSQL RLS/concurrency/index proof, full regression, backend smoke/OpenAPI docs sync, frontend lint/typecheck/build, relevant complete Playwright suite, query-budget evidence, clean branch and verified push.

**Final acceptance criteria:**
- HR creates, updates, transitions and archives employees.
- Employee number/email uniqueness remains race-safe.
- Own/team/tenant and field-level views are API-enforced.
- Manager cannot access protected fields via API or frontend.
- Employee 360 avoids per-tab/per-row N+1 queries.
- Hard delete is unavailable to normal roles.
- Profile change request/decision works end to end.
- No mail, document, leave-policy, payroll or sensitive-identifier scope leaked into Phase 4.

## Review/deploy rule

Push only the Phase 4 review branch after green checkpoints. Do not merge `main` or deploy staging without Murat’s explicit review approval.
