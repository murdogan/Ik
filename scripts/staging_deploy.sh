#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REPO_URL="${IK_STAGING_REPO_URL:-https://github.com/murdogan/Ik.git}"
BRANCH="${IK_STAGING_BRANCH:-main}"
APP_DIR="${IK_STAGING_APP_DIR:-/opt/data/staging/ik-app}"
PORT="${IK_STAGING_PORT:-8001}"
HOST="${IK_STAGING_HOST:-0.0.0.0}"
WEB_PORT="${IK_STAGING_WEB_PORT:-3001}"
WEB_HOST="${IK_STAGING_WEB_HOST:-127.0.0.1}"
PID_FILE="${IK_STAGING_PID_FILE:-/opt/data/staging/ik-app.pid}"
LOG_FILE="${IK_STAGING_LOG_FILE:-/opt/data/staging/ik-app.log}"
WEB_PID_FILE="${IK_STAGING_WEB_PID_FILE:-/opt/data/staging/ik-web.pid}"
WEB_LOG_FILE="${IK_STAGING_WEB_LOG_FILE:-/opt/data/staging/ik-web.log}"
NOTIFICATION_PID_FILE="${IK_STAGING_NOTIFICATION_PID_FILE:-/opt/data/staging/ik-notification-worker.pid}"
NOTIFICATION_LOG_FILE="${IK_STAGING_NOTIFICATION_LOG_FILE:-/opt/data/staging/ik-notification-worker.log}"
REPORTING_PID_FILE="${IK_STAGING_REPORTING_PID_FILE:-/opt/data/staging/ik-reporting-worker.pid}"
REPORTING_LOG_FILE="${IK_STAGING_REPORTING_LOG_FILE:-/opt/data/staging/ik-reporting-worker.log}"
REV_FILE="${IK_STAGING_REV_FILE:-/opt/data/staging/ik-app.rev}"
LOCK_FILE="${IK_STAGING_LOCK_FILE:-/opt/data/staging/ik-app.deploy.lock}"
BASE_URL="${IK_STAGING_BASE_URL:-http://127.0.0.1:${PORT}}"
RELEASE_ROOT="${IK_STAGING_RELEASE_ROOT:-/opt/data/staging/ik-releases}"
NODE_MAX_OLD_SPACE_MB="${IK_STAGING_NODE_MAX_OLD_SPACE_MB:-512}"

if [[ ! "$NODE_MAX_OLD_SPACE_MB" =~ ^[0-9]+$ ]] \
  || (( NODE_MAX_OLD_SPACE_MB < 256 || NODE_MAX_OLD_SPACE_MB > 2048 )); then
  echo "DEPLOY_FAILED: invalid frontend Node heap limit." >&2
  exit 1
fi

mkdir -p "$(dirname "$APP_DIR")" "$(dirname "$PID_FILE")"
exec 9> "$LOCK_FILE"
if ! flock -n 9; then
  echo "DEPLOY_FAILED: another staging deployment is active." >&2
  exit 1
fi

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

(
  cd frontend
  export NODE_OPTIONS="--max-old-space-size=${NODE_MAX_OLD_SPACE_MB}"
  npm ci
  npm run typecheck
  npm run lint
  BACKEND_API_URL="http://127.0.0.1:${PORT}" NEXT_TELEMETRY_DISABLED=1 npm run build
)

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

spawn_service() {
  local pid_file="$1"
  local role="$2"
  local log_file="$3"
  shift 3
  python3 - "$pid_file" "$role" "$APP_DIR" "$log_file" "$@" <<'PY'
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import tempfile
import time

pid_path = Path(sys.argv[1])
role = sys.argv[2]
app_dir = Path(sys.argv[3]).resolve(strict=True)
log_path = Path(sys.argv[4])
command = sys.argv[5:]
release_sha = os.environ.get("IK_RELEASE_COMMIT_SHA", "")
expected_cwd_by_role = {
    "api": app_dir,
    "web": app_dir / "frontend",
    "notification": app_dir,
    "reporting": app_dir,
}
if role not in expected_cwd_by_role or not command:
    raise SystemExit("DEPLOY_FAILED: invalid service launch request")
if re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
    raise SystemExit("DEPLOY_FAILED: invalid service release identity")
expected_cwd = expected_cwd_by_role[role]
log_descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
process = None
pidfd = None
temporary_path = None
identity_installed = False
try:
    process = subprocess.Popen(
        command,
        cwd=expected_cwd,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=log_descriptor,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    os.close(log_descriptor)
    log_descriptor = -1
    pidfd = os.pidfd_open(process.pid)
    process_starttime = None
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError("service exited during identity capture")
        try:
            proc = Path("/proc") / str(process.pid)
            status = (proc / "status").read_text(encoding="ascii")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            process_uids = {int(value) for value in uid_line.split()[1:]}
            process_cwd = Path(os.readlink(proc / "cwd")).resolve(strict=True)
            command_parts = (proc / "cmdline").read_bytes().split(b"\0")
            command_text = b"\0".join(part for part in command_parts if part).decode(
                "utf-8", "strict"
            )
            environment = (proc / "environ").read_bytes().split(b"\0")
            stat_fields = (
                (proc / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            )
            process_parent = int(stat_fields[1])
            candidate_starttime = stat_fields[19]
            role_matches = {
                "api": "uvicorn" in command_text and "app.main:app" in command_text,
                "web": "next-server" in command_text
                or ("node_modules/.bin/next" in command_text and "start" in command_text),
                "notification": "app.workers.notifications" in command_text,
                "reporting": "app.workers.reporting" in command_text,
            }
            if (
                process_uids == {os.geteuid()}
                and process_cwd == expected_cwd
                and process_parent == os.getpid()
                and role_matches[role]
                and f"IK_RELEASE_COMMIT_SHA={release_sha}".encode() in environment
            ):
                process_starttime = candidate_starttime
                break
        except (OSError, StopIteration, UnicodeError, ValueError, IndexError):
            pass
        time.sleep(0.01)
    if process_starttime is None:
        raise RuntimeError("service identity capture timed out")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{pid_path.name}.tmp.", dir=pid_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, f"{process.pid} {process_starttime}\n".encode("ascii"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary_path, pid_path)
    temporary_path = None
    identity_installed = True
    print(process.pid, process_starttime)
except BaseException as error:
    if pidfd is not None:
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if not poller.poll(2000):
            try:
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            poller.poll(2000)
    elif process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if identity_installed:
        try:
            if pid_path.read_text(encoding="ascii").strip() == (
                f"{process.pid} {process_starttime}"
            ):
                pid_path.unlink()
        except (OSError, UnicodeError):
            pass
    raise SystemExit(f"DEPLOY_FAILED: service launch failed ({type(error).__name__})") from None
finally:
    if log_descriptor >= 0:
        os.close(log_descriptor)
    if pidfd is not None:
        os.close(pidfd)
    if temporary_path is not None:
        temporary_path.unlink(missing_ok=True)
PY
}

stop_pid_file() {
  local pid_file="$1"
  local role="$2"
  local action="${3:-stop}"
  local expected_release="${4:-}"
  local pid_override="${5:-}"
  local starttime_override="${6:-}"
  local expected_parent="${7:-}"
  python3 - "$pid_file" "$role" "$APP_DIR" "$action" "$expected_release" \
    "$pid_override" "$starttime_override" "$expected_parent" <<'PY'
import os
from pathlib import Path
import re
import select
import signal
import stat
import sys

pid_path = Path(sys.argv[1])
role = sys.argv[2]
app_dir = Path(sys.argv[3]).resolve(strict=True)
action = sys.argv[4]
expected_release = sys.argv[5]
pid_override = sys.argv[6]
starttime_override = sys.argv[7]
expected_parent = sys.argv[8]
expected_cwd_by_role = {
    "api": app_dir,
    "web": app_dir / "frontend",
    "notification": app_dir,
    "reporting": app_dir,
}
if role not in expected_cwd_by_role:
    raise SystemExit("DEPLOY_FAILED: unknown process role")
if action not in {"stop", "verify"}:
    raise SystemExit("DEPLOY_FAILED: unknown process action")
if pid_override:
    raw_pid = pid_override
    recorded_starttime = starttime_override
else:
    try:
        descriptor = os.open(pid_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except FileNotFoundError:
        if action == "verify":
            raise SystemExit("DEPLOY_FAILED: PID file missing") from None
        raise SystemExit(0) from None
    except OSError:
        raise SystemExit("DEPLOY_FAILED: unsafe PID file") from None
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        os.close(descriptor)
        raise SystemExit("DEPLOY_FAILED: unsafe PID file")
    try:
        with os.fdopen(descriptor, "r", encoding="ascii") as stream:
            identity_fields = stream.read(128).strip().split()
    except (OSError, UnicodeError):
        raise SystemExit("DEPLOY_FAILED: unreadable PID file") from None
    if len(identity_fields) != 2:
        raise SystemExit("DEPLOY_FAILED: invalid PID identity file")
    raw_pid, recorded_starttime = identity_fields
if (
    re.fullmatch(r"[1-9][0-9]*", raw_pid) is None
    or re.fullmatch(r"[1-9][0-9]*", recorded_starttime) is None
):
    raise SystemExit("DEPLOY_FAILED: invalid PID identity")
pid = int(raw_pid)
try:
    pidfd = os.pidfd_open(pid)
except ProcessLookupError:
    if not pid_override:
        pid_path.unlink(missing_ok=True)
    if action == "verify":
        raise SystemExit("DEPLOY_FAILED: process exited") from None
    raise SystemExit(0) from None
try:
    proc = Path("/proc") / raw_pid
    status = (proc / "status").read_text(encoding="ascii")
    uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
    process_uids = {int(value) for value in uid_line.split()[1:]}
    process_cwd = Path(os.readlink(proc / "cwd")).resolve(strict=True)
    command = (proc / "cmdline").read_bytes().split(b"\0")
    command_text = b"\0".join(part for part in command if part).decode("utf-8", "strict")
    environment = (proc / "environ").read_bytes().split(b"\0")
    release_values = [
        item.split(b"=", 1)[1].decode("ascii", "strict")
        for item in environment
        if item.startswith(b"IK_RELEASE_COMMIT_SHA=")
    ]
    stat_fields = (proc / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
    process_parent = int(stat_fields[1])
    process_starttime = stat_fields[19]
except (OSError, StopIteration, UnicodeError, ValueError, IndexError):
    raise SystemExit("DEPLOY_FAILED: process identity unavailable") from None
role_matches = {
    "api": "uvicorn" in command_text and "app.main:app" in command_text,
    "web": "next-server" in command_text
    or ("node_modules/.bin/next" in command_text and "start" in command_text),
    "notification": "app.workers.notifications" in command_text,
    "reporting": "app.workers.reporting" in command_text,
}
if (
    process_uids != {os.geteuid()}
    or process_cwd != expected_cwd_by_role[role]
    or not role_matches[role]
    or len(release_values) != 1
    or re.fullmatch(r"[0-9a-f]{40}", expected_release) is None
    or release_values[0] != expected_release
    or (recorded_starttime and process_starttime != recorded_starttime)
    or (expected_parent and process_parent != int(expected_parent))
):
    raise SystemExit("DEPLOY_FAILED: PID identity mismatch")

if action == "verify":
    os.close(pidfd)
    raise SystemExit(0)

poller = select.poll()
poller.register(pidfd, select.POLLIN)
try:
    signal.pidfd_send_signal(pidfd, signal.SIGTERM)
except ProcessLookupError:
    pass
if not poller.poll(4000):
    try:
        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if not poller.poll(2000):
        raise SystemExit("DEPLOY_FAILED: process did not stop")
os.close(pidfd)
pid_path.unlink(missing_ok=True)
PY
}

verify_pid_file() {
  stop_pid_file "$1" "$2" verify "$3"
}

stop_pid_value() {
  stop_pid_file "$1" "$2" stop "$5" "$3" "$4"
}

stop_pid_file "$PID_FILE" api stop "$last_deployed"
stop_pid_file "$WEB_PID_FILE" web stop "$last_deployed"
stop_pid_file "$NOTIFICATION_PID_FILE" notification stop "$last_deployed"
stop_pid_file "$REPORTING_PID_FILE" reporting stop "$last_deployed"

deployment_committed=0
new_pid=""
new_starttime=""
web_pid=""
web_starttime=""
notification_pid=""
notification_starttime=""
reporting_pid=""
reporting_starttime=""
cleanup_failed_deploy() {
  local status="$?"
  local cleanup_failed=0
  trap - EXIT
  if [[ "$deployment_committed" != "1" ]]; then
    if [[ -n "$new_pid" && -n "$new_starttime" ]]; then
      stop_pid_value "$PID_FILE" api "$new_pid" "$new_starttime" "$release_commit_sha" || cleanup_failed=1
    fi
    if [[ -n "$web_pid" && -n "$web_starttime" ]]; then
      stop_pid_value "$WEB_PID_FILE" web "$web_pid" "$web_starttime" "$release_commit_sha" || cleanup_failed=1
    fi
    if [[ -n "$notification_pid" && -n "$notification_starttime" ]]; then
      stop_pid_value "$NOTIFICATION_PID_FILE" notification "$notification_pid" "$notification_starttime" "$release_commit_sha" || cleanup_failed=1
    fi
    if [[ -n "$reporting_pid" && -n "$reporting_starttime" ]]; then
      stop_pid_value "$REPORTING_PID_FILE" reporting "$reporting_pid" "$reporting_starttime" "$release_commit_sha" || cleanup_failed=1
    fi
    if [[ "$cleanup_failed" == "1" ]]; then
      echo "DEPLOY_FAILED: one or more new processes require manual cleanup." >&2
    fi
  fi
  exit "$status"
}
trap cleanup_failed_deploy EXIT

: > "$LOG_FILE"
: > "$WEB_LOG_FILE"
: > "$NOTIFICATION_LOG_FILE"
: > "$REPORTING_LOG_FILE"
export IK_RELEASE_COMMIT_SHA="$release_commit_sha"
export IK_RELEASE_BUILD_TIMESTAMP="$release_build_timestamp"
export PYTHONPATH=backend
export BACKEND_API_URL="http://127.0.0.1:${PORT}"
export NEXT_TELEMETRY_DISABLED=1

read -r new_pid new_starttime <<< "$(
  spawn_service "$PID_FILE" api "$LOG_FILE" \
    .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"
)"
read -r web_pid web_starttime <<< "$(
  spawn_service "$WEB_PID_FILE" web "$WEB_LOG_FILE" \
    ./node_modules/.bin/next start --hostname "$WEB_HOST" --port "$WEB_PORT"
)"
read -r notification_pid notification_starttime <<< "$(
  spawn_service "$NOTIFICATION_PID_FILE" notification "$NOTIFICATION_LOG_FILE" \
    .venv/bin/python -m app.workers.notifications
)"
read -r reporting_pid reporting_starttime <<< "$(
  spawn_service "$REPORTING_PID_FILE" reporting "$REPORTING_LOG_FILE" \
    .venv/bin/python -m app.workers.reporting
)"

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
  echo "DEPLOY_FAILED: app did not become ready. Review restricted log: $LOG_FILE" >&2
  exit 1
fi

web_ready=0
for _ in {1..50}; do
  if curl -fsS --connect-timeout 1 --max-time 2 "http://${WEB_HOST}:${WEB_PORT}/" >/dev/null 2>&1; then
    web_ready=1
    break
  fi
  sleep 0.2
done
if [[ "$web_ready" != "1" ]]; then
  echo "DEPLOY_FAILED: web did not become ready. Review restricted log: $WEB_LOG_FILE" >&2
  exit 1
fi
uv run --no-sync python - "http://${WEB_HOST}:${WEB_PORT}" <<'PY'
import sys
import urllib.error
import urllib.request

base_url = sys.argv[1]
for path in ("/", "/manifest.webmanifest", "/sw.js"):
    with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
        if response.status != 200:
            raise SystemExit(1)
        body = response.read()
        if not body:
            raise SystemExit(1)
        if path == "/manifest.webmanifest" and "no-cache" not in response.headers.get(
            "Cache-Control", ""
        ):
            raise SystemExit(1)
        if path == "/sw.js":
            cache_control = response.headers.get("Cache-Control", "")
            if "no-store" not in cache_control or response.headers.get(
                "Service-Worker-Allowed"
            ) != "/":
                raise SystemExit(1)
try:
    urllib.request.urlopen(f"{base_url}/api/v1/tenant/readiness", timeout=5)
except urllib.error.HTTPError as error:
    if error.code != 401:
        raise SystemExit(1) from None
else:
    raise SystemExit(1)
PY

if ! verify_pid_file "$WEB_PID_FILE" web "$release_commit_sha"; then
  echo "DEPLOY_FAILED: web process identity invalid. Review restricted log: $WEB_LOG_FILE" >&2
  exit 1
fi
if ! verify_pid_file "$NOTIFICATION_PID_FILE" notification "$release_commit_sha"; then
  echo "DEPLOY_FAILED: notification worker identity invalid. Review restricted log: $NOTIFICATION_LOG_FILE" >&2
  exit 1
fi
if ! verify_pid_file "$REPORTING_PID_FILE" reporting "$release_commit_sha"; then
  echo "DEPLOY_FAILED: reporting worker identity invalid. Review restricted log: $REPORTING_LOG_FILE" >&2
  exit 1
fi
verify_pid_file "$PID_FILE" api "$release_commit_sha"

uv run --no-sync python scripts/staging_smoke_test.py "$BASE_URL"
verify_pid_file "$PID_FILE" api "$release_commit_sha"
verify_pid_file "$WEB_PID_FILE" web "$release_commit_sha"
verify_pid_file "$NOTIFICATION_PID_FILE" notification "$release_commit_sha"
verify_pid_file "$REPORTING_PID_FILE" reporting "$release_commit_sha"
echo "$remote_rev" > "$REV_FILE"
deployment_committed=1
trap - EXIT
echo "DEPLOY_OK branch=${BRANCH} rev=${remote_rev} api_url=${BASE_URL} web_url=http://${WEB_HOST}:${WEB_PORT} pid=${new_pid} web_pid=${web_pid} notification_pid=${notification_pid} reporting_pid=${reporting_pid} previous=${current_rev}"
