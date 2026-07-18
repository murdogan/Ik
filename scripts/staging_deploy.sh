#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REPO_URL="${IK_STAGING_REPO_URL:-https://github.com/murdogan/Ik.git}"
BRANCH="${IK_STAGING_BRANCH:-main}"
APP_DIR="${IK_STAGING_APP_DIR:-/opt/data/staging/ik-app}"
PORT="${IK_STAGING_PORT:-8001}"
HOST="${IK_STAGING_HOST:-0.0.0.0}"
PID_FILE="${IK_STAGING_PID_FILE:-/opt/data/staging/ik-app.pid}"
LOG_FILE="${IK_STAGING_LOG_FILE:-/opt/data/staging/ik-app.log}"
NOTIFICATION_PID_FILE="${IK_STAGING_NOTIFICATION_PID_FILE:-/opt/data/staging/ik-notification-worker.pid}"
NOTIFICATION_LOG_FILE="${IK_STAGING_NOTIFICATION_LOG_FILE:-/opt/data/staging/ik-notification-worker.log}"
REPORTING_PID_FILE="${IK_STAGING_REPORTING_PID_FILE:-/opt/data/staging/ik-reporting-worker.pid}"
REPORTING_LOG_FILE="${IK_STAGING_REPORTING_LOG_FILE:-/opt/data/staging/ik-reporting-worker.log}"
REV_FILE="${IK_STAGING_REV_FILE:-/opt/data/staging/ik-app.rev}"
BASE_URL="${IK_STAGING_BASE_URL:-http://127.0.0.1:${PORT}}"
RELEASE_ROOT="${IK_STAGING_RELEASE_ROOT:-/opt/data/staging/ik-releases}"

mkdir -p "$(dirname "$APP_DIR")" "$(dirname "$PID_FILE")"

if [[ ! -d "$APP_DIR/.git" ]]; then
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch origin "$BRANCH:refs/remotes/origin/$BRANCH"
remote_rev="$(git rev-parse "origin/${BRANCH}")"
if [[ ! "$remote_rev" =~ ^[0-9a-f]{40}$ ]]; then
  echo "DEPLOY_FAILED: invalid remote revision." >&2
  exit 1
fi
current_rev="$(git rev-parse HEAD 2>/dev/null || true)"
last_deployed="$(cat "$REV_FILE" 2>/dev/null || true)"

if [[ "$remote_rev" == "$last_deployed" ]] && [[ "${IK_STAGING_FORCE:-0}" != "1" ]]; then
  echo "NO_CHANGE rev=${remote_rev}"
  exit 0
fi

git checkout -B "$BRANCH" "origin/$BRANCH"
git reset --hard "$remote_rev"
checked_out_rev="$(git rev-parse HEAD)"
if [[ "$checked_out_rev" != "$remote_rev" ]]; then
  echo "DEPLOY_FAILED: checked-out revision mismatch." >&2
  exit 1
fi

uv sync --frozen --all-groups
uv run --no-sync ruff check backend scripts/ops
uv run --no-sync ruff format --check \
  backend/app/api/health.py \
  backend/app/api/tenant_readiness.py \
  backend/app/core/config.py \
  backend/app/main.py \
  backend/app/platform/observability \
  backend/app/schemas/health.py \
  backend/app/schemas/tenant_readiness.py \
  backend/app/services/tenant_readiness_service.py \
  backend/app/workers/notifications.py \
  backend/app/workers/reporting.py \
  scripts/ops
uv run --no-sync python -m compileall -q backend/app scripts/ops

IK_ENVIRONMENT=local \
IK_RELEASE_COMMIT_SHA=development \
IK_RELEASE_BUILD_TIMESTAMP=1970-01-01T00:00:00Z \
PYTHONPATH=backend \
uv run --no-sync python - <<'PY'
import json

from app.main import create_app

schema = create_app().openapi()
if schema.get("security") not in (None, []):
    raise SystemExit(1)
paths = schema.get("paths")
if type(paths) is not dict:
    raise SystemExit(1)

operations = {}
for path in ("/health/live", "/health/ready", "/api/v1/tenant/readiness"):
    path_item = paths.get(path)
    if type(path_item) is not dict or type(path_item.get("get")) is not dict:
        raise SystemExit(1)
    operations[path] = path_item["get"]

for path in ("/health/live", "/health/ready"):
    if operations[path].get("security") not in (None, []):
        raise SystemExit(1)
if operations["/api/v1/tenant/readiness"].get("security") != [{"BearerAuth": []}]:
    raise SystemExit(1)
components = schema.get("components")
if type(components) is not dict:
    raise SystemExit(1)
security_schemes = components.get("securitySchemes")
bearer_auth = security_schemes.get("BearerAuth") if type(security_schemes) is dict else None
if (
    type(bearer_auth) is not dict
    or bearer_auth.get("type") != "http"
    or bearer_auth.get("scheme") != "bearer"
):
    raise SystemExit(1)

json.dumps(schema, sort_keys=True, separators=(",", ":"))
PY

uv run --no-sync alembic heads

build_timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
if [[ ! "$build_timestamp" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
  echo "DEPLOY_FAILED: invalid build timestamp." >&2
  exit 1
fi
release_stamp="${build_timestamp//[-:]/}"
release_dir="${RELEASE_ROOT}/${remote_rev}-${release_stamp}-$$"
if [[ -L "$RELEASE_ROOT" ]]; then
  echo "DEPLOY_FAILED: unsafe release root." >&2
  exit 1
fi
mkdir -p -m 0700 -- "$RELEASE_ROOT"
if [[ -L "$RELEASE_ROOT" || ! -d "$RELEASE_ROOT" ]]; then
  echo "DEPLOY_FAILED: unsafe release root." >&2
  exit 1
fi
mkdir -m 0700 -- "$release_dir"

release_manifest_name="release-manifest.json"
release_manifest="${release_dir}/${release_manifest_name}"
uv run --no-sync python scripts/ops/release_manifest.py \
  --output "$release_manifest" \
  --commit-sha "$remote_rev" \
  --build-timestamp "$build_timestamp" \
  >/dev/null

(
  cd "$release_dir"
  sha256sum --check --strict --status "${release_manifest_name}.sha256"
)

release_identity_output="$(
  uv run --no-sync python - "$release_manifest" "$remote_rev" "$build_timestamp" <<'PY'
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


def object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def read_private_file(path: Path, maximum_bytes: int) -> bytes:
    metadata = path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size > maximum_bytes
            or before.st_dev != metadata.st_dev
            or before.st_ino != metadata.st_ino
            or (hasattr(os, "geteuid") and before.st_uid != os.geteuid())
        ):
            raise ValueError
        chunks = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(data) > maximum_bytes
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise ValueError
        return data
    finally:
        os.close(descriptor)


try:
    manifest_path = Path(sys.argv[1])
    checksum_path = Path(f"{manifest_path}.sha256")
    release_directory = manifest_path.parent.lstat()
    if (
        not stat.S_ISDIR(release_directory.st_mode)
        or stat.S_IMODE(release_directory.st_mode) != 0o700
        or (hasattr(os, "geteuid") and release_directory.st_uid != os.geteuid())
    ):
        raise ValueError

    manifest_bytes = read_private_file(manifest_path, 65_536)
    checksum_bytes = read_private_file(checksum_path, 4_096)
    manifest = json.loads(
        manifest_bytes.decode("utf-8", "strict"),
        object_pairs_hook=object_without_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
    )
    if type(manifest) is not dict or set(manifest) != {
        "app_version",
        "build_timestamp_utc",
        "compatible_migration_head_ids",
        "release_commit_sha",
    }:
        raise ValueError
    canonical = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")
    if manifest_bytes != canonical:
        raise ValueError

    commit_sha = manifest["release_commit_sha"]
    timestamp = manifest["build_timestamp_utc"]
    app_version = manifest["app_version"]
    migration_heads = manifest["compatible_migration_head_ids"]
    if type(commit_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ValueError
    if type(timestamp) is not str or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", timestamp
    ) is None:
        raise ValueError
    parsed_timestamp = dt.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)
    if parsed_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") != timestamp:
        raise ValueError
    if type(app_version) is not str or re.fullmatch(
        r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}", app_version
    ) is None:
        raise ValueError
    if type(migration_heads) is not list or not 1 <= len(migration_heads) <= 64:
        raise ValueError
    if any(
        type(head) is not str or len(head) > 128 or re.fullmatch(r"[0-9a-z_]+", head) is None
        for head in migration_heads
    ) or migration_heads != sorted(set(migration_heads)):
        raise ValueError
    if commit_sha != sys.argv[2] or timestamp != sys.argv[3]:
        raise ValueError

    digest = hashlib.sha256(manifest_bytes).hexdigest()
    expected_checksum = f"{digest}  {manifest_path.name}\n".encode("ascii")
    if checksum_bytes != expected_checksum:
        raise ValueError
except Exception:
    raise SystemExit(1) from None

sys.stdout.write(f"{commit_sha}\n{timestamp}\n")
PY
)"
mapfile -t release_identity <<< "$release_identity_output"
if [[ "${#release_identity[@]}" -ne 2 ]]; then
  echo "DEPLOY_FAILED: invalid release identity." >&2
  exit 1
fi
release_commit_sha="${release_identity[0]}"
release_build_timestamp="${release_identity[1]}"
if [[ "$release_commit_sha" != "$remote_rev" || "$release_build_timestamp" != "$build_timestamp" ]]; then
  echo "DEPLOY_FAILED: release identity mismatch." >&2
  exit 1
fi
unset release_identity_output release_identity

stop_pid_file() {
  local pid_file="$1"
  local old_pid
  if [[ ! -f "$pid_file" ]]; then
    return
  fi
  old_pid="$(cat "$pid_file" || true)"
  if [[ -z "$old_pid" ]] || ! [[ "$old_pid" =~ ^[1-9][0-9]*$ ]]; then
    return
  fi
  if kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid" || true
    for _ in {1..20}; do
      if ! kill -0 "$old_pid" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "$old_pid" 2>/dev/null; then
      kill -9 "$old_pid" || true
    fi
  fi
}

stop_pid_file "$PID_FILE"
stop_pid_file "$NOTIFICATION_PID_FILE"
stop_pid_file "$REPORTING_PID_FILE"

: > "$LOG_FILE"
: > "$NOTIFICATION_LOG_FILE"
: > "$REPORTING_LOG_FILE"
IK_RELEASE_COMMIT_SHA="$release_commit_sha" \
IK_RELEASE_BUILD_TIMESTAMP="$release_build_timestamp" \
PYTHONPATH=backend \
nohup uv run --no-sync uvicorn app.main:app --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
new_pid="$!"
echo "$new_pid" > "$PID_FILE"

IK_RELEASE_COMMIT_SHA="$release_commit_sha" \
IK_RELEASE_BUILD_TIMESTAMP="$release_build_timestamp" \
PYTHONPATH=backend \
nohup uv run --no-sync python -m app.workers.notifications >> "$NOTIFICATION_LOG_FILE" 2>&1 &
notification_pid="$!"
echo "$notification_pid" > "$NOTIFICATION_PID_FILE"

IK_RELEASE_COMMIT_SHA="$release_commit_sha" \
IK_RELEASE_BUILD_TIMESTAMP="$release_build_timestamp" \
PYTHONPATH=backend \
nohup uv run --no-sync python -m app.workers.reporting >> "$REPORTING_LOG_FILE" 2>&1 &
reporting_pid="$!"
echo "$reporting_pid" > "$REPORTING_PID_FILE"

ready=0
for _ in {1..50}; do
  if curl -fsS --connect-timeout 1 --max-time 2 "${BASE_URL}/health/ready" 2>/dev/null \
    | uv run --no-sync python -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (UnicodeDecodeError, ValueError):
    raise SystemExit(1) from None
raise SystemExit(0 if type(payload) is dict and payload.get("commit_sha") == sys.argv[1] else 1)
' "$remote_rev" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.2
done

if [[ "$ready" != "1" ]]; then
  echo "DEPLOY_FAILED: app did not become ready. Log:" >&2
  tail -80 "$LOG_FILE" >&2 || true
  exit 1
fi

if ! kill -0 "$notification_pid" 2>/dev/null; then
  echo "DEPLOY_FAILED: notification worker exited. Log:" >&2
  tail -80 "$NOTIFICATION_LOG_FILE" >&2 || true
  exit 1
fi
if ! kill -0 "$reporting_pid" 2>/dev/null; then
  echo "DEPLOY_FAILED: reporting worker exited. Log:" >&2
  tail -80 "$REPORTING_LOG_FILE" >&2 || true
  exit 1
fi

uv run --no-sync python scripts/staging_smoke_test.py "$BASE_URL"
echo "$remote_rev" > "$REV_FILE"
echo "DEPLOY_OK branch=${BRANCH} rev=${remote_rev} url=${BASE_URL} pid=${new_pid} notification_pid=${notification_pid} reporting_pid=${reporting_pid} previous=${current_rev}"
