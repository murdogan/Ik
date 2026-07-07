# IK Overnight Codex Full-Night Backlog Plan

> **For Hermes:** This is a planning/control document for tonight's Codex run. Do not execute it until Murat explicitly approves the overnight run. Use Codex CLI with `gpt-5.5`, `model_reasoning_effort="xhigh"`, and the existing safe supervisor/cron pattern.

**Goal:** Keep Codex productively working from 00:00–05:00 TR without going idle early, while producing understandable HRMS backend progress: real APIs, DB-backed dashboard, validation, tests, seed/demo data, and documentation.

**Architecture:** Continue from review branch `develop/wealthy-falcon-review`. Work on a fresh branch for tonight, preserving the pushed review branch. Follow the backend order strictly: data/session foundation → dashboard real data → employee schemas/API → leave schemas/API → demo seed → docs/review. Do not jump ahead to UI work.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, ruff, Codex CLI, git branches, Hermes cron supervisor.

---

## 0. Dün Geceki Ders

Dün gece Codex yaklaşık 00:30–03:00 TR arası aktif çalıştı ve sonra task kuyruğu bitti. Bu gece aynı hata yapılmayacak.

Bu plan iki kuyruklu:

1. **Primary Queue:** Mutlaka yapılması istenen ürün işleri.
2. **Overflow Queue:** Primary erken biterse 04:30'a kadar devam edecek ek işler.

Cron supervisor artık sadece `done=all` görünce boş beklememeli; overflow queue’dan sıradaki güvenli işi almalı.

---

## 1. Başlangıç Kuralları

### Branch

Bu gece yeni branch açılacak:

```bash
git fetch origin
git switch develop/wealthy-falcon-review
git pull --ff-only origin develop/wealthy-falcon-review
git switch -c overnight/2026-07-07-product-crud
```

### Codex mode

Her task:

```bash
codex exec \
  -m gpt-5.5 \
  -c 'model_reasoning_effort="xhigh"' \
  --sandbox danger-full-access \
  "<TASK_PROMPT>"
```

### Hard rules

- No main merge.
- No production/staging deploy unless the explicit task says staging preview smoke and all gates are green.
- No secrets/env/token edits.
- No payroll, SGK, bank, PDKS, AI, external integrations.
- No fake data as real business data. Demo seed must be clearly named demo.
- Follow SOLID: small routers/services/schemas, no god modules, no unnecessary abstraction.
- TDD preferred: tests first for every API behavior.
- Every task must run:

```bash
uv run ruff check backend
uv run pytest -q
```

- Commit only when gates pass.

### Stop rules

Stop giving new feature tasks when:

- tests fail twice on same task,
- migration breaks upgrade/downgrade logic,
- task touches forbidden files,
- 04:30 TR reached and current task is not tiny cleanup,
- there is a merge conflict or unreviewable giant diff.

---

## 2. Primary Queue — Must Do

### P0 — Preflight and branch prep

**Objective:** Start from pushed review branch and verify clean baseline.

**Files:**
- Modify: `.hermes/overnight/task-queue.md`

**Steps:**
1. Confirm branch clean.
2. Run `uv run ruff check backend`.
3. Run `uv run pytest -q`.
4. Create tonight task queue file.
5. Commit: `docs(P0): prepare full-night product backlog branch`.

**Expected:** baseline green.

---

### P1 — Replace hardcoded dashboard with DB-backed service

**Objective:** `/api/v1/dashboard/summary` must stop returning fake hardcoded numbers and count from DB/query layer.

**Files:**
- Modify: `backend/app/api/dashboard.py`
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/services/dashboard_service.py`
- Test: `backend/tests/test_dashboard.py`

**Acceptance:**
- Endpoint response model remains stable.
- Counts are calculated from employees and leave_requests.
- Empty DB/demo dependency returns zeros, not 42/6 fake numbers.
- Tests prove no hardcoded dashboard constants remain.

**Verification:**

```bash
uv run pytest backend/tests/test_dashboard.py -q
uv run ruff check backend
uv run pytest -q
```

**Commit:** `feat(P1): make dashboard summary database backed`

---

### P2 — Employee schemas and validation

**Objective:** Add explicit request/response schemas for employee APIs.

**Files:**
- Create: `backend/app/schemas/employee.py`
- Test: `backend/tests/test_employee_schemas.py`

**Acceptance:**
- `EmployeeCreate`
- `EmployeeUpdate`
- `EmployeeRead`
- Validates non-empty names.
- Validates email format if provided.
- Keeps tenant_id server-side, not client-controlled.
- Uses simple Pydantic models, no overengineering.

**Commit:** `feat(P2): add employee API schemas`

---

### P3 — Employee CRUD API

**Objective:** Implement visible backend functionality for employee management.

**Files:**
- Create: `backend/app/api/employees.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/services/employee_service.py` if needed
- Test: `backend/tests/test_employee_api.py`

**Endpoints:**

```text
GET    /api/v1/employees
POST   /api/v1/employees
GET    /api/v1/employees/{employee_id}
PATCH  /api/v1/employees/{employee_id}
DELETE /api/v1/employees/{employee_id}
```

**Acceptance:**
- Tests cover create/list/detail/update/delete.
- Tenant scope is represented even if temporary dependency is demo/test tenant context.
- 404 for unknown employee.
- Cannot create duplicate employee_number within same tenant.
- Delete is either hard delete or status-based soft delete, but decision must be documented in test name/README note.

**Commit:** `feat(P3): add employee CRUD API`

---

### P4 — Leave request schemas and validation

**Objective:** Add explicit request/response schemas for leave requests.

**Files:**
- Create: `backend/app/schemas/leave_request.py`
- Test: `backend/tests/test_leave_request_schemas.py`

**Acceptance:**
- `LeaveRequestCreate`
- `LeaveRequestRead`
- `LeaveRequestDecision`
- Validates `end_date >= start_date`.
- Status lifecycle is explicit.
- Client cannot directly create an approved request unless endpoint is decision endpoint.

**Commit:** `feat(P4): add leave request API schemas`

---

### P5 — Leave request API

**Objective:** Implement leave request list/create/detail and approval decision endpoints.

**Files:**
- Create: `backend/app/api/leave_requests.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/services/leave_request_service.py` if needed
- Test: `backend/tests/test_leave_request_api.py`

**Endpoints:**

```text
GET   /api/v1/leave-requests
POST  /api/v1/leave-requests
GET   /api/v1/leave-requests/{leave_request_id}
POST  /api/v1/leave-requests/{leave_request_id}/approve
POST  /api/v1/leave-requests/{leave_request_id}/reject
POST  /api/v1/leave-requests/{leave_request_id}/cancel
```

**Acceptance:**
- Pending request can be approved/rejected/cancelled.
- Approved/rejected request cannot be approved again.
- Reject supports decision_note.
- Date validation tested.
- Employee belongs to same tenant check is represented/tested.

**Commit:** `feat(P5): add leave request workflow API`

---

### P6 — Demo seed data command/script

**Objective:** Make dashboard and APIs easy to preview with realistic demo records.

**Files:**
- Create: `backend/app/demo_seed.py` or `scripts/seed_demo_data.py`
- Test: `backend/tests/test_demo_seed.py`
- Modify: `README.md`

**Acceptance:**
- Creates one demo tenant.
- Creates demo users/employees/leave requests.
- Idempotent: running twice does not duplicate employee_number.
- Clearly labels demo data.
- README has exact command.

**Commit:** `feat(P6): add idempotent demo seed data`

---

### P7 — OpenAPI/documentation sync

**Objective:** Docs match implemented endpoints.

**Files:**
- Modify: `docs/09-uygulama/03-openapi-endpoint-taslagi.md`
- Modify: `README.md`
- Optional: create `docs/09-uygulama/11-api-implementation-status.md`

**Acceptance:**
- Employee endpoints documented.
- Leave request endpoints documented.
- Dashboard summary documented as DB-backed.
- Remaining TODOs explicit.

**Commit:** `docs(P7): sync API docs with implemented endpoints`

---

## 3. Overflow Queue — Continue If Primary Finishes Early

These are ordered. Supervisor should keep launching until 04:30 TR if gates are green.

### O1 — Organization/departments minimal model

**Objective:** Add minimal department support only if needed for dashboard distribution.

**Files:**
- Create migration `0005_create_departments.py` only if justified.
- Or avoid migration and normalize department as string for now.

**Preferred:** Avoid new table unless Codex can justify it. YAGNI.

**Commit:** `feat(O1): improve department distribution support`

---

### O2 — Employee filtering and pagination

**Objective:** Improve employee list endpoint with useful query params.

**Acceptance:**
- `status`
- `department`
- `search`
- `limit/offset` with sane bounds
- tests

**Commit:** `feat(O2): add employee list filters`

---

### O3 — Leave request filtering

**Objective:** Improve leave request list endpoint.

**Acceptance:**
- filter by status, employee_id, date range
- tests

**Commit:** `feat(O3): add leave request filters`

---

### O4 — Dashboard richer cards

**Objective:** Add more DB-backed dashboard fields without hardcoded numbers.

**Acceptance:**
- active employees
- on-leave employees
- pending requests
- new starters this month
- department distribution
- tests with seeded records

**Commit:** `feat(O4): enrich dashboard summary cards`

---

### O5 — Backend smoke and API contract review

**Objective:** If backend is green and branch is clean, run local API smoke checks without UI or deploy.

**Acceptance:**
- No deploy.
- No frontend/UI work.
- Run app locally if current scaffold supports it.
- Hit `/health`, `/`, `/api/v1/dashboard/summary`, employee endpoints, leave request endpoints.
- Produce report file.

**Commit:** `test(O5): add backend API smoke report`

---

### O6 — GitHub review branch push

**Objective:** Push tonight branch so Murat can see code.

**Acceptance:**
- Push branch to GitHub.
- If `.github/workflows` token-scope blocks push, omit workflow changes or document blocker.
- Return compare URL in final report.

**Commit:** Only if needed before push.

---

## 4. Supervisor Logic Fixes for Tonight

### Required orchestrator changes

The current orchestrator must not stop at `done=primary`. It needs:

```text
if primary_queue_done and time < 04:30:
    load overflow_queue
    start next safe overflow task
```

### Minimum queue size

Tonight queue must contain at least:

- 8 primary tasks
- 6 overflow tasks

Expected active work: 5+ hours.

### Progress reporting

Every 15 minutes:

```text
HH:MM TR
current task
elapsed task time
queue primary done/pending
queue overflow done/pending
ruff/pytest last result
last commit
risk/blocker
```

### If Codex finishes early again

If all primary + overflow tasks finish before 04:30:

1. Do not invent random features.
2. Run full review:
   - `git diff --stat main..HEAD`
   - `uv run ruff check backend`
   - `uv run pytest -q`
   - inspect API docs vs routes
3. Push review branch if safe.
4. Generate detailed report.

---

## 5. Quality Gates

Before each commit:

```bash
uv run ruff check backend
uv run pytest -q
```

Before final report:

```bash
git status --short
uv run ruff check backend
uv run pytest -q
git log --oneline --max-count=15
git diff --stat develop/wealthy-falcon-review..HEAD
```

If a task changes migrations, also run:

```bash
uv run alembic heads
uv run alembic history
```

If local Postgres is unavailable, do not claim DB migration runtime success; say only static Alembic chain verified.

---

## 6. Expected Final Output Tomorrow Morning

The 05:05 report must include:

- Active coding window.
- Tasks completed by ID.
- Tasks skipped/blockers.
- Commit list.
- Test result.
- Diff stat.
- Branch URL if pushed.
- Clear statement: backend-only progress; no UI expected.
- Next recommended merge/review action.

---

## 7. Main Risk

The repo currently has limited DB/session/API dependency infrastructure. Employee/Leave CRUD may require adding session management/test DB utilities. That is acceptable if kept small and tested.

If Codex cannot safely implement real DB persistence within the current scaffold, it must stop and write a blocker report instead of building fake in-memory APIs.

---

## 8. Tonight Success Definition

Successful night means at least:

- Employee CRUD API implemented and tested.
- Leave request workflow API implemented and tested.
- Dashboard summary no longer hardcoded.
- Demo seed exists or blocker explained.
- Tests green.
- Branch pushed for GitHub review.

If only docs/model changes happen again, the night is considered under-scoped.
