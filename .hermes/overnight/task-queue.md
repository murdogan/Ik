# Overnight Codex Task Queue

## T0 — Baseline and branch preparation

Status: done

Prepare branch, commit planning files if needed, run baseline ruff/pytest. Do not implement product features.

## T1 — README and local development commands

Status: done

Update README/local docs with uv, pytest, ruff, smoke-test, branch workflow commands. Docs only unless a tiny config fix is required.

## T2 — CI workflow

Status: done

Add GitHub Actions CI running ruff and pytest for backend. Keep it minimal.

## T3 — Alembic / migration foundation

Status: done

Inspect existing migration foundation; add or repair minimal Alembic setup only if needed. Document commands. No destructive migrations.

## T4 — Tenant/User foundation hardening

Status: done

Harden existing tenant/user models and tenant isolation helpers/tests. Keep scope minimal.

## T5 — Employee minimal model

Status: done

Add tenant-scoped Employee model and tests using documented MVP fields.

## T6 — Leave request minimal model

Status: done

Add tenant-scoped LeaveRequest model and tests with pending/approved/rejected/cancelled statuses.

## T7 — Dashboard summary endpoint

Status: pending

Add /api/v1/dashboard/summary endpoint and tests for first demo cards.

## T8 — Landing brand update

Status: pending

Update landing brand text to Wealthy Falcon HR while preserving approved design. Update tests.

## T9 — Final cleanup and report

Status: pending

Run final cleanup, tests, ruff, and create a concise implementation report. Do not start major new features.
