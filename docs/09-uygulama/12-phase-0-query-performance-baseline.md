# Phase 0 Query Performance Baseline (P0F)

Date: 2026-07-10
Scope: employee/leave list pagination, employee search and dashboard query count

Historical note: this document preserves the P0F capture and its then-current employee
`(employee_number asc, id asc)` plan evidence. P4A later superseded only the employee directory
ordering with `Employee.id ASC`; the captured timings/index evidence below was not rerun for that
repair and must not be read as repaired PostgreSQL execution evidence.

## Contract and safeguards

- `GET /api/v1/employees` keeps its plain JSON array response and bounded `offset` path for
  compatibility. The preferred growing-list path uses `cursor`; a following page is advertised by
  `X-Next-Cursor`. At P0F capture time, ordering was `(employee_number asc, id asc)`; the current
  P4A contract uses `Employee.id ASC` with the exact continuation predicate
  `Employee.id > cursor.id`.
- `GET /api/v1/leave-requests` uses the same additive contract. Its cursor contains the full
  `(created_at desc, start_date asc, id asc)` ordering tuple. Mixed directions are applied
  explicitly in the keyset predicate.
- Cursors are opaque, versioned, endpoint-specific base64url JSON. They never carry or grant tenant
  scope; the server tenant predicate is always applied independently. Malformed cursors and
  `cursor` combined with positive `offset` return the existing module-specific `422` envelope.
- Employee `q` remains case-insensitive literal substring search over employee number and email.
  PostgreSQL uses native `ILIKE`, with `%`, `_` and the escape character escaped as data.
- `pg_trgm` partial GIN indexes cover non-archived employee number and email searches. Exact
  department filtering reads a stored generated normalization
  `lower(ltrim(rtrim(department)))` through `(tenant_id, department_normalized)`.
- The dashboard count cards are one conditional aggregate statement, reducing the default summary
  from 7 to 4 SQL statements. With recent activity disabled the bound is reduced from 5 to 2.
  Department distribution and the two compatibility-sensitive activity reads remain separate.
- No Redis client, cache key, cache invalidation path, or new cache dependency was added. The
  measured query/index changes meet the Phase 0 need without speculative caching.

## Representative data and repeat procedure

The PostgreSQL-only regression creates a disposable Alembic-migrated database and seeds one tenant
with exactly 10,000 employees and 5,000 dependent leave requests. Employee data varies lifecycle
status, four departments, start/end dates, numbers and emails; leave data varies type, status,
dates and timestamps. After the bulk load it runs `VACUUM (ANALYZE)` before collecting plans.

```bash
docker compose up -d --wait postgres
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres \
  uv run pytest -q -m postgres \
  backend/tests/integration/test_postgresql_p0f_performance.py -s
```

The fixture treats `IK_TEST_DATABASE_URL` only as an administration DSN, creates a uniquely named
temporary database, and drops that database after the run. It does not seed, migrate, truncate or
downgrade the database named in the DSN. The test prints one machine-readable
`P0F_EXPLAIN_EVIDENCE=...` line.

## Captured PostgreSQL 16.4 evidence

The following warm-cache evidence was captured on 2026-07-10 from the procedure above on local
arm64 PostgreSQL 16.4. Every plan used `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`; block totals are
the root plan's query totals. `Rows removed` is summed across plan nodes and is bounded for cursor
queries so an index scan that merely filters every preceding page cannot pass.

| Query | Actual rows | Rows removed | Index evidence | Planning ms | Execution ms | Shared hit/read blocks |
|---|---:|---:|---|---:|---:|---:|
| Selective employee substring search | 1 | 0 | `ix_employees_email_trgm`, `ix_employees_employee_number_trgm` | 0.672 | 0.791 | 86 / 0 |
| Employee page after `WF-005000` | 51 | 1 | `uq_employees_tenant_employee_number` | 0.227 | 0.115 | 5 / 0 |
| Leave page after the 2,500th request | 51 | 1 | `ix_leave_requests_tenant_created_cursor` | 0.464 | 0.066 | 5 / 0 |
| Consolidated dashboard counts | 1 | 1,250 | full tenant aggregate; sequential scan is expected | 0.167 | 5.618 | 332 / 0 |

The regression builds EXPLAIN statements through the same production SQLAlchemy query builders and
asserts cursor rows-removed bounds plus critical index names, not wall-clock thresholds. Timing is
recorded as baseline evidence but is hardware-, cache- and load-sensitive. The master-plan targets
(employee list p95 below 300 ms and dashboard below 1 s) still require a repeatable concurrency/
p95 profile before pilot; this Phase 0 check prevents plan-shape and query-count regressions.

Short search strings or low-selectivity values may correctly make PostgreSQL choose a sequential
scan. Trigram eligibility is proven with a selective representative term; no breaking minimum
search length was introduced. Dashboard full-tenant aggregates are likewise not forced through an
index when PostgreSQL estimates a sequential scan is cheaper.
