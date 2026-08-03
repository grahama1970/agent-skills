#!/usr/bin/env bash
set -euo pipefail

# Dewey nightly monitor-sparta cron wrapper.
# The Python runner owns the state machine; this wrapper only provides cron-safe
# locking, environment alignment, and top-level logs.

MEMORY_ROOT="${MEMORY_ROOT:-${MEMORY_REPO_ROOT:-/home/graham/workspace/experiments/memory}}"
AGENT_SKILLS_ROOT="${AGENT_SKILLS_ROOT:-/home/graham/workspace/experiments/agent-skills}"
DEWEY_SESSION_BASE="${DEWEY_SESSION_BASE:-${DEWEY_SESSION_ROOT:-/mnt/storage12tb/skills/review-db/outputs/dewey-sessions}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DAY="$(date -u +%Y%m%d)"
REQUESTED_RUN_ID="${DEWEY_RUN_ID:-}"
DEWEY_SKIP_BACKUP="${DEWEY_SKIP_BACKUP:-auto}"
RUN_ID="${REQUESTED_RUN_ID:-dewey-monitor-sparta-${RUN_DAY}}"
if [[ -z "${REQUESTED_RUN_ID}" && "${DEWEY_SKIP_BACKUP}" == "auto" ]]; then
  REUSABLE_RUN_ID="$(python3 - "${DEWEY_SESSION_BASE}" "${RUN_DAY}" <<'PY'
import json
import pathlib
import sys

base = pathlib.Path(sys.argv[1])
day = sys.argv[2]
best: pathlib.Path | None = None
for path in base.glob(f"*{day}*"):
    if not path.is_dir():
        continue
    receipt_path = path / "backup_receipt.json"
    session_path = path / "session.json"
    if not receipt_path.is_file() or not session_path.is_file():
        continue
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    backup_dir = pathlib.Path(str(receipt.get("backup_dir") or ""))
    if not (backup_dir / "dump.json").is_file():
        continue
    if session.get("status") not in {"committed", "verified"}:
        continue
    if best is None or path.stat().st_mtime > best.stat().st_mtime:
        best = path
if best is not None:
    print(best.name)
PY
)"
  if [[ -n "${REUSABLE_RUN_ID}" ]]; then
    RUN_ID="${REUSABLE_RUN_ID}"
  fi
fi
CRON_LOG_DIR="${MEMORY_ROOT}/artifacts/dewey_nightly/${RUN_ID}"
LOCK_FILE="${MEMORY_ROOT}/artifacts/dewey_nightly/dewey-monitor-sparta.lock"

mkdir -p "${CRON_LOG_DIR}" "$(dirname "${LOCK_FILE}")" "${DEWEY_SESSION_BASE}"

export MEMORY_ROOT
export AGENT_SKILLS_ROOT
export DEWEY_SESSION_BASE
export DEWEY_RUN_ID="${RUN_ID}"
export DEWEY_SCILLM_CHUTES_CALL_BUDGET="${DEWEY_SCILLM_CHUTES_CALL_BUDGET:-5000}"
export DEWEY_MAX_ITERATIONS="${DEWEY_MAX_ITERATIONS:-${DEWEY_SCILLM_CHUTES_CALL_BUDGET}}"
export DEWEY_WALL_CLOCK_S="${DEWEY_WALL_CLOCK_S:-86400}"
export DEWEY_HARD_TIMEOUT_S="${DEWEY_HARD_TIMEOUT_S:-$((DEWEY_WALL_CLOCK_S + 900))}"
export DEWEY_WAIT_TIMEOUT_S="${DEWEY_WAIT_TIMEOUT_S:-7200}"
export DEWEY_WORKER_POLL_S="${DEWEY_WORKER_POLL_S:-30}"
export DEWEY_EMBED_BATCH_LIMIT="${DEWEY_EMBED_BATCH_LIMIT:-50}"
export DEWEY_SKIP_BACKUP
export DEWEY_PROCESS_HEARTBEAT_S="${DEWEY_PROCESS_HEARTBEAT_S:-60}"
export DEWEY_SUBPROCESS_HEARTBEAT_S="${DEWEY_SUBPROCESS_HEARTBEAT_S:-60}"
export DEWEY_CHILD_HEARTBEAT_S="${DEWEY_CHILD_HEARTBEAT_S:-${DEWEY_SUBPROCESS_HEARTBEAT_S}}"
export DEWEY_REPAIR_TIMEOUT_S="${DEWEY_REPAIR_TIMEOUT_S:-${DEWEY_WALL_CLOCK_S}}"
export DEWEY_SCILLM_QRA_HTTP_TIMEOUT_S="${DEWEY_SCILLM_QRA_HTTP_TIMEOUT_S:-7200}"
export DEWEY_SCILLM_QRA_SINGLE_ITEM_TIMEOUT_S="${DEWEY_SCILLM_QRA_SINGLE_ITEM_TIMEOUT_S:-7200}"
export DEWEY_CREATE_QRAS_REVIEW_TIMEOUT_S="${DEWEY_CREATE_QRAS_REVIEW_TIMEOUT_S:-3600}"
export DEWEY_CREATE_QRAS_DRY_RUN_TIMEOUT_S="${DEWEY_CREATE_QRAS_DRY_RUN_TIMEOUT_S:-3600}"
export DEWEY_CREATE_QRAS_CANARY_TIMEOUT_S="${DEWEY_CREATE_QRAS_CANARY_TIMEOUT_S:-21600}"
export DEWEY_CREATE_QRAS_CANARY_ATTEMPTS="${DEWEY_CREATE_QRAS_CANARY_ATTEMPTS:-2}"
export DEWEY_CREATE_QRAS_CANARY_RETRY_BASE_S="${DEWEY_CREATE_QRAS_CANARY_RETRY_BASE_S:-300}"
export DEWEY_CREATE_QRAS_STORE_RETRY_ATTEMPTS="${DEWEY_CREATE_QRAS_STORE_RETRY_ATTEMPTS:-4}"
export DEWEY_CREATE_QRAS_STORE_RETRY_BASE_S="${DEWEY_CREATE_QRAS_STORE_RETRY_BASE_S:-30}"
export DEWEY_MONITOR_HEALTH_TIMEOUT_S="${DEWEY_MONITOR_HEALTH_TIMEOUT_S:-7200}"
export DEWEY_ARANGO_BACKUP_TIMEOUT_S="${DEWEY_ARANGO_BACKUP_TIMEOUT_S:-21600}"
export DEWEY_HEALTH_JSON_TIMEOUT_S="${DEWEY_HEALTH_JSON_TIMEOUT_S:-300}"
export DEWEY_HEALTH_FIX_TIMEOUT_S="${DEWEY_HEALTH_FIX_TIMEOUT_S:-240}"
export DEWEY_STALL_LIMIT="${DEWEY_STALL_LIMIT:-8}"

SESSION_DIR="${DEWEY_SESSION_BASE}/${RUN_ID}"
EFFECTIVE_SKIP_BACKUP="0"
if [[ "${DEWEY_SKIP_BACKUP}" == "1" || "${DEWEY_SKIP_BACKUP,,}" == "true" ]]; then
  EFFECTIVE_SKIP_BACKUP="1"
elif [[ "${DEWEY_SKIP_BACKUP}" == "auto" && -f "${SESSION_DIR}/backup_receipt.json" && -f "${SESSION_DIR}/session.json" ]]; then
  EFFECTIVE_SKIP_BACKUP="1"
fi

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Dewey monitor-sparta already running; lock=${LOCK_FILE}" | tee -a "${CRON_LOG_DIR}/cron.log"
  exit 75
fi

{
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "run_id=${RUN_ID}"
  echo "requested_run_id=${REQUESTED_RUN_ID:-auto}"
  echo "run_stamp=${RUN_STAMP}"
  echo "memory_repo_root=${MEMORY_ROOT}"
  echo "agent_skills_root=${AGENT_SKILLS_ROOT}"
  echo "dewey_session_base=${DEWEY_SESSION_BASE}"
  echo "max_cycles=${DEWEY_MAX_ITERATIONS} scillm_chutes_call_budget=${DEWEY_SCILLM_CHUTES_CALL_BUDGET} wall_clock_s=${DEWEY_WALL_CLOCK_S} hard_timeout_s=${DEWEY_HARD_TIMEOUT_S} wait_timeout_s=${DEWEY_WAIT_TIMEOUT_S} worker_poll_s=${DEWEY_WORKER_POLL_S} embed_batch_limit=${DEWEY_EMBED_BATCH_LIMIT} skip_backup=${DEWEY_SKIP_BACKUP} effective_skip_backup=${EFFECTIVE_SKIP_BACKUP} process_heartbeat_s=${DEWEY_PROCESS_HEARTBEAT_S} subprocess_heartbeat_s=${DEWEY_SUBPROCESS_HEARTBEAT_S} child_heartbeat_s=${DEWEY_CHILD_HEARTBEAT_S} repair_timeout_s=${DEWEY_REPAIR_TIMEOUT_S} scillm_qra_http_timeout_s=${DEWEY_SCILLM_QRA_HTTP_TIMEOUT_S} scillm_qra_single_item_timeout_s=${DEWEY_SCILLM_QRA_SINGLE_ITEM_TIMEOUT_S} create_qras_review_timeout_s=${DEWEY_CREATE_QRAS_REVIEW_TIMEOUT_S} create_qras_dry_run_timeout_s=${DEWEY_CREATE_QRAS_DRY_RUN_TIMEOUT_S} create_qras_canary_timeout_s=${DEWEY_CREATE_QRAS_CANARY_TIMEOUT_S} create_qras_canary_attempts=${DEWEY_CREATE_QRAS_CANARY_ATTEMPTS} create_qras_canary_retry_base_s=${DEWEY_CREATE_QRAS_CANARY_RETRY_BASE_S} create_qras_store_retry_attempts=${DEWEY_CREATE_QRAS_STORE_RETRY_ATTEMPTS} create_qras_store_retry_base_s=${DEWEY_CREATE_QRAS_STORE_RETRY_BASE_S} monitor_health_timeout_s=${DEWEY_MONITOR_HEALTH_TIMEOUT_S} arango_backup_timeout_s=${DEWEY_ARANGO_BACKUP_TIMEOUT_S} health_json_timeout_s=${DEWEY_HEALTH_JSON_TIMEOUT_S} health_fix_timeout_s=${DEWEY_HEALTH_FIX_TIMEOUT_S} stall_limit=${DEWEY_STALL_LIMIT}"
} >> "${CRON_LOG_DIR}/cron.log"

START_ARGS=(
  start
  --run-id "${RUN_ID}"
  --session-root "${DEWEY_SESSION_BASE}"
  --memory-repo-root "${MEMORY_ROOT}"
  --agent-skills-root "${AGENT_SKILLS_ROOT}"
  --max-cycles "${DEWEY_MAX_ITERATIONS}"
  --wall-clock-s "${DEWEY_WALL_CLOCK_S}"
  --wait-timeout-s "${DEWEY_WAIT_TIMEOUT_S}"
  --embed-batch-limit "${DEWEY_EMBED_BATCH_LIMIT}"
  --repair-timeout-s "${DEWEY_REPAIR_TIMEOUT_S}"
  --health-json-timeout-s "${DEWEY_HEALTH_JSON_TIMEOUT_S}"
  --health-fix-timeout-s "${DEWEY_HEALTH_FIX_TIMEOUT_S}"
  --stall-limit "${DEWEY_STALL_LIMIT}"
  --json
)
if [[ "${EFFECTIVE_SKIP_BACKUP}" == "1" ]]; then
  START_ARGS+=(--no-backup)
fi

set +e
if command -v timeout >/dev/null 2>&1; then
  timeout --preserve-status "${DEWEY_HARD_TIMEOUT_S}" \
    "${PYTHON_BIN}" "${SCRIPT_DIR}/dewey_overnight_run.py" "${START_ARGS[@]}" \
    > "${CRON_LOG_DIR}/dewey_overnight.stdout.json" \
    2> "${CRON_LOG_DIR}/dewey_overnight.stderr.log"
else
  "${PYTHON_BIN}" "${SCRIPT_DIR}/dewey_overnight_run.py" "${START_ARGS[@]}" \
    > "${CRON_LOG_DIR}/dewey_overnight.stdout.json" \
    2> "${CRON_LOG_DIR}/dewey_overnight.stderr.log"
fi
rc=$?
set -e

SESSION_RECEIPT="${SESSION_DIR}/nightly_receipt.json"
SESSION_SUMMARY="${SESSION_DIR}/dewey_evidence_summary.json"
CRON_RECEIPT="${CRON_LOG_DIR}/nightly_receipt.json"
CRON_SUMMARY="${CRON_LOG_DIR}/dewey_evidence_summary.json"
if [[ -f "${SESSION_RECEIPT}" ]]; then
  cp "${SESSION_RECEIPT}" "${CRON_RECEIPT}"
fi
if [[ -f "${SESSION_SUMMARY}" ]]; then
  cp "${SESSION_SUMMARY}" "${CRON_SUMMARY}"
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/dewey_overnight_run.py" status \
  --session-root "${DEWEY_SESSION_BASE}" \
  --run-id "${RUN_ID}" \
  --json > "${CRON_LOG_DIR}/dewey_status.json" 2>> "${CRON_LOG_DIR}/dewey_overnight.stderr.log" || true

{
  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "exit_code=${rc}"
  echo "stdout_json=${CRON_LOG_DIR}/dewey_overnight.stdout.json"
  echo "stderr_log=${CRON_LOG_DIR}/dewey_overnight.stderr.log"
  echo "session_dir=${SESSION_DIR}"
  if [[ -f "${CRON_RECEIPT}" ]]; then
    echo "nightly_receipt=${CRON_RECEIPT}"
  else
    echo "nightly_receipt=missing"
  fi
  if [[ -f "${CRON_SUMMARY}" ]]; then
    echo "evidence_summary=${CRON_SUMMARY}"
  else
    echo "evidence_summary=missing"
  fi
  echo "status_json=${CRON_LOG_DIR}/dewey_status.json"
} >> "${CRON_LOG_DIR}/cron.log"

exit "${rc}"
