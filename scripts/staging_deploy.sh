#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${IK_STAGING_REPO_URL:-https://github.com/murdogan/Ik.git}"
BRANCH="${IK_STAGING_BRANCH:-main}"
APP_DIR="${IK_STAGING_APP_DIR:-/opt/data/staging/ik-app}"
PORT="${IK_STAGING_PORT:-8001}"
HOST="${IK_STAGING_HOST:-0.0.0.0}"
PID_FILE="${IK_STAGING_PID_FILE:-/opt/data/staging/ik-app.pid}"
LOG_FILE="${IK_STAGING_LOG_FILE:-/opt/data/staging/ik-app.log}"
REV_FILE="${IK_STAGING_REV_FILE:-/opt/data/staging/ik-app.rev}"
BASE_URL="${IK_STAGING_BASE_URL:-http://127.0.0.1:${PORT}}"

mkdir -p "$(dirname "$APP_DIR")" "$(dirname "$PID_FILE")"

if [[ ! -d "$APP_DIR/.git" ]]; then
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch origin "$BRANCH"
remote_rev="$(git rev-parse "origin/${BRANCH}")"
current_rev="$(git rev-parse HEAD 2>/dev/null || true)"
last_deployed="$(cat "$REV_FILE" 2>/dev/null || true)"

if [[ "$remote_rev" == "$last_deployed" ]] && [[ "${IK_STAGING_FORCE:-0}" != "1" ]]; then
  echo "NO_CHANGE rev=${remote_rev}"
  exit 0
fi

git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"

uv sync --all-groups
uv run ruff check backend
uv run pytest

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
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
fi

: > "$LOG_FILE"
PYTHONPATH=backend nohup uv run uvicorn app.main:app --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
new_pid="$!"
echo "$new_pid" > "$PID_FILE"

ready=0
for _ in {1..50}; do
  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
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

uv run python scripts/staging_smoke_test.py "$BASE_URL"
echo "$remote_rev" > "$REV_FILE"
echo "DEPLOY_OK branch=${BRANCH} rev=${remote_rev} url=${BASE_URL} pid=${new_pid} previous=${current_rev}"
