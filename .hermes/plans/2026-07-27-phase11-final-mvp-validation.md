# Phase 11 — Final MVP Validation, Repair, and Acceptance

Date: 2026-07-27
Base: `origin/main` at `160aa8aa30836642ee00d9fadad6a62dcdee079b`
Branch: `codex/mvp-phase11-final-validation`
Worktree: `/opt/data/repos/Ik-mvp-phase11`

## Objective

Complete the planned HRMS MVP with one exhaustive validation-and-repair phase. Phase 11 is not report-only: demonstrated defects are repaired, affected lanes are rerun, and the complete final gate is rerun once after repairs. At completion, produce an evidence-backed residual-gap report that distinguishes MVP blockers from post-MVP/V1 work.

## Fixed scope

- Full backend regression and current OpenAPI/runtime smoke.
- Clean disposable PostgreSQL 17 migration, downgrade/drift, RLS, ACL, tenant-isolation, command/concurrency, and representative query-plan lanes.
- Full frontend lint, typecheck, production build, and all current Playwright journeys.
- Persona/authorization matrix for platform admin, tenant admin, HR, manager, and employee; direct-route denial and zero privileged-call assertions where applicable.
- Cross-tenant/BOLA checks for tenant-owned records, exports, files, reports, notifications, privacy, employee, leave, organization, and self-service surfaces.
- Critical identity journeys: invite/activation, email-first login, organization selection, platform realm separation, refresh rotation/reuse, forgot/reset password, session revocation.
- Critical product journeys: organization, employee master/360/account link/change request, document upload/scan/download boundaries, leave request/approval/balance, announcements/notifications, reports/exports/imports, privacy requests/consents/retention evidence.
- Security/dependency/secret scan and production-dependency audit; repository-owned release/recovery gates.
- Staging acceptance on one immutable pushed SHA after all local gates are green.

## Explicit exclusions

- No new V1/V2 feature families such as ATS, payroll engine, performance/OKR, PDKS product module, webhook productization, or native mobile app.
- No production deployment.
- No `main` merge by Codex. Final merge remains supervisor-owned after Phase 11 acceptance.
- No test-count inflation or duplicate harnesses merely to increase coverage. Reuse and repair current suites; add tests only for demonstrated gaps or regressions.
- Never use real PII. Use deterministic synthetic data and disposable databases/storage targets.

## Continuous execution blocks

### P11A — Inventory and baseline

1. Inventory current API operations, frontend routes, test files/case counts, markers, Playwright projects, migrations, RLS tables/policies, dependency gates, and staging/recovery scripts.
2. Run read-only collection first (`pytest --collect-only`, `playwright test --list`) and record counts.
3. Establish baseline failures without changing product behavior. Classify environment/harness drift separately from product defects.

### P11B — Full backend regression and contract repair

1. Run full default backend regression, Ruff check and format check.
2. Run backend API smoke and OpenAPI/metadata/contract checks.
3. Repair demonstrated product, authorization, transaction, schema, or harness defects.
4. Rerun affected nodes, then the complete default backend lane.

### P11C — PostgreSQL migration, RLS, isolation, and data integrity

1. Use only the disposable local PostgreSQL 17 proof cluster/DSN; never staging or operational DB.
2. Run the complete `-m postgres` lane including base→head→base where supported, model drift, current head, capability-role ACLs, FORCE RLS, tenant A/B direct SQL isolation, FK/constraint/concurrency/idempotency, and query-plan checks.
3. Repair demonstrated defects and rerun the affected lane, then complete PostgreSQL regression.
4. Preserve immutable historical migrations; add a forward migration only if a real schema defect requires it.

### P11D — Frontend and persona E2E matrix

1. Clean install, typecheck, lint, production build.
2. List and run all existing Playwright tests on Chromium using the configured executable.
3. Ensure critical MVP journeys and five persona boundaries are executable. Add/repair journeys only where a current MVP flow or denial is untested/broken.
4. Verify protected management UI is absent and privileged endpoint calls are zero for unauthorized personas.
5. Rerun affected specs, then the complete Playwright suite once.

### P11E — Security, dependencies, and representative performance

1. Run secret scan/pattern scan without printing credential values.
2. Run backend/frontend dependency checks; production dependency audit must have no high/critical findings.
3. Exercise upload malware/scanner fail-closed behavior, presigned-object tenant binding, export privacy/masking, recovery confirmation/empty-target guards, and PWA authenticated-data no-cache contract.
4. Run existing representative query-plan/performance checks; report measured evidence without inventing unsupported SLO claims.
5. Fix Critical/High and MVP P1/P2 defects. Record lower residuals if safe to defer.

### P11F — Final full gate, staging acceptance, and gap report

1. From a clean committed review branch, rerun the complete backend, PostgreSQL, frontend build, Playwright, security/dependency, smoke, and release-manifest gates once.
2. Push and verify exact branch SHA and CI.
3. Supervisor deploys that exact SHA to staging, verifies migration head, four-process identity, API/web/public smoke, production audit, lock release, and release manifest checksum.
4. Produce `.hermes/P11_WORK_LOG.md` with exact commands, case counts, pass/fail/skip, defects fixed, residual risks, and post-MVP gap report.
5. Completion criteria: no open Critical/High or MVP P1/P2 defect; all required lanes pass or an external environment-only limitation is explicitly evidenced and does not hide untested product behavior.

## Agent operating contract

- Use Codex CLI with model `gpt-5.6-sol`, reasoning effort `ultra`.
- Continue across P11A–P11F without waiting for manual approval between blocks unless there is a destructive decision, credential requirement, true product-contract ambiguity, or external blocker that cannot be repaired safely.
- Preserve architecture, tenant/RLS/auth boundaries, API compatibility, audit redaction, maintainability, and performance. No artificial LOC limits.
- Commit coherent repair checkpoints and push only `codex/mvp-phase11-final-validation`; never merge or deploy.
- Keep `.hermes/P11_WORK_LOG.md` current and redact all credentials/connection strings/tokens as `[REDACTED]`.
- Do not modify or commit runtime credentials, OAuth files, staging state, generated browser artifacts, test databases, object-store data, PID/log/env files, or external tools.
