#!/usr/bin/env bash
set -euo pipefail

# Cron wrapper for Dewey one-issue DBA worker.
# One cron activation must claim at most one monitor-sparta repair issue.

MEMORY_ROOT="${MEMORY_ROOT:-${MEMORY_REPO_ROOT:-/home/graham/workspace/experiments/memory}}"
AGENT_SKILLS_ROOT="${AGENT_SKILLS_ROOT:-/home/graham/workspace/experiments/agent-skills}"
DEWEY_SESSION_BASE="${DEWEY_SESSION_BASE:-${DEWEY_SESSION_ROOT:-/mnt/storage12tb/skills/review-db/outputs/dewey-sessions}}"
MONITOR_SPARTA_STATE_DIR="${MONITOR_SPARTA_STATE_DIR:-/mnt/storage12tb/media/agents/shared/monitor-sparta}"
DEWEY_REPAIR_QUEUE="${DEWEY_REPAIR_QUEUE:-${MONITOR_SPARTA_STATE_DIR}/repair_queue.jsonl}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DAY="$(date -u +%Y%m%d)"
RUN_ID="${DEWEY_RUN_ID:-dewey-${RUN_STAMP}}"
CRON_LOG_DIR="${MEMORY_ROOT}/artifacts/dewey_nightly/${RUN_ID}"
LOCK_FILE="${MEMORY_ROOT}/artifacts/dewey_nightly/dewey-one-issue.lock"

mkdir -p "${CRON_LOG_DIR}" "$(dirname "${LOCK_FILE}")" "${DEWEY_SESSION_BASE}" "$(dirname "${DEWEY_REPAIR_QUEUE}")"

export MEMORY_ROOT AGENT_SKILLS_ROOT MONITOR_SPARTA_STATE_DIR DEWEY_SESSION_BASE
export DEWEY_LANE_TIMEOUT_S="${DEWEY_LANE_TIMEOUT_S:-${DEWEY_REPAIR_TIMEOUT_S:-7200}}"
export DEWEY_HEALTH_JSON_TIMEOUT_S="${DEWEY_HEALTH_JSON_TIMEOUT_S:-300}"
# Queue construction is monitor-sparta owned.  This bootstrap limit is only for
# optional read-only queue bootstrapping; embedding apply lanes are full-scope
# and use DEWEY_EMBED_SCAN_BATCH_SIZE/DEWEY_EMBED_BATCH_SIZE for internal chunks.
export DEWEY_BOOTSTRAP_LIMIT="${DEWEY_BOOTSTRAP_LIMIT:-0}"
export DEWEY_EMBED_SCAN_BATCH_SIZE="${DEWEY_EMBED_SCAN_BATCH_SIZE:-500}"
export DEWEY_EMBED_BATCH_SIZE="${DEWEY_EMBED_BATCH_SIZE:-16}"
export DEWEY_SUBPROCESS_HEARTBEAT_S="${DEWEY_SUBPROCESS_HEARTBEAT_S:-60}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Dewey already running; lock=${LOCK_FILE}" | tee -a "${CRON_LOG_DIR}/cron.log"
  exit 75
fi

APPLY_ARGS=()
if [[ "${DEWEY_DRY_RUN:-0}" == "1" || "${DEWEY_DRY_RUN:-false}" == "true" ]]; then
  :
else
  APPLY_ARGS+=(--apply)
fi

BOOTSTRAP_ARGS=()
if [[ "${DEWEY_NO_BOOTSTRAP:-0}" == "1" || "${DEWEY_NO_BOOTSTRAP:-false}" == "true" ]]; then
  BOOTSTRAP_ARGS+=(--no-bootstrap)
fi

{
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "run_id=${RUN_ID}"
  echo "run_day=${RUN_DAY}"
  echo "memory_repo_root=${MEMORY_ROOT}"
  echo "agent_skills_root=${AGENT_SKILLS_ROOT}"
  echo "dewey_session_base=${DEWEY_SESSION_BASE}"
  echo "monitor_sparta_state_dir=${MONITOR_SPARTA_STATE_DIR}"
  echo "repair_queue=${DEWEY_REPAIR_QUEUE}"
  echo "dry_run=${DEWEY_DRY_RUN:-0}"
  echo "lane_timeout_s=${DEWEY_LANE_TIMEOUT_S}"
  echo "health_json_timeout_s=${DEWEY_HEALTH_JSON_TIMEOUT_S}"
  echo "bootstrap_limit=${DEWEY_BOOTSTRAP_LIMIT}"
  echo "embed_scan_batch_size=${DEWEY_EMBED_SCAN_BATCH_SIZE}"
  echo "embed_batch_size=${DEWEY_EMBED_BATCH_SIZE}"
} >> "${CRON_LOG_DIR}/cron.log"

set +e
"${PYTHON_BIN}" "${SCRIPT_DIR}/dewey_issue_worker.py" run \
  --run-id "${RUN_ID}" \
  --run-root "${DEWEY_SESSION_BASE}" \
  --queue "${DEWEY_REPAIR_QUEUE}" \
  --memory-repo-root "${MEMORY_ROOT}" \
  --agent-skills-root "${AGENT_SKILLS_ROOT}" \
  --timeout-s "${DEWEY_LANE_TIMEOUT_S}" \
  --health-timeout-s "${DEWEY_HEALTH_JSON_TIMEOUT_S}" \
  --bootstrap-limit "${DEWEY_BOOTSTRAP_LIMIT}" \
  --heartbeat-s "${DEWEY_SUBPROCESS_HEARTBEAT_S}" \
  "${APPLY_ARGS[@]}" \
  "${BOOTSTRAP_ARGS[@]}" \
  --json \
  > "${CRON_LOG_DIR}/dewey_issue_worker.stdout.json" \
  2> "${CRON_LOG_DIR}/dewey_issue_worker.stderr.log"
rc=$?
set -e

SESSION_DIR="${DEWEY_SESSION_BASE}/${RUN_ID}"
for name in receipt.json nightly_receipt.json dewey_evidence_summary.json issue.json lane_result.json bootstrap.json; do
  if [[ -f "${SESSION_DIR}/${name}" ]]; then
    cp "${SESSION_DIR}/${name}" "${CRON_LOG_DIR}/${name}"
  fi
done

"${PYTHON_BIN}" "${SCRIPT_DIR}/dewey_issue_worker.py" status \
  --queue "${DEWEY_REPAIR_QUEUE}" \
  --json > "${CRON_LOG_DIR}/dewey_queue_status.json" \
  2>> "${CRON_LOG_DIR}/dewey_issue_worker.stderr.log" || true

{
  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "exit_code=${rc}"
  echo "stdout_json=${CRON_LOG_DIR}/dewey_issue_worker.stdout.json"
  echo "stderr_log=${CRON_LOG_DIR}/dewey_issue_worker.stderr.log"
  echo "session_dir=${SESSION_DIR}"
  echo "receipt=${CRON_LOG_DIR}/receipt.json"
  echo "queue_status=${CRON_LOG_DIR}/dewey_queue_status.json"
} >> "${CRON_LOG_DIR}/cron.log"

exit "${rc}"
