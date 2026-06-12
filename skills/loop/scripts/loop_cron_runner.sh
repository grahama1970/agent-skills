#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: loop_cron_runner.sh <repo> <prompt_file> <log_dir>" >&2
  exit 2
fi

REPO="$1"
PROMPT_FILE="$2"
LOG_DIR="$3"
mkdir -p "$LOG_DIR"
cd "$REPO"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
STDOUT_LOG="$LOG_DIR/${RUN_ID}.stdout"
STDERR_LOG="$LOG_DIR/${RUN_ID}.stderr"
MANIFEST="$LOG_DIR/${RUN_ID}.manifest.json"
LOCK_DIR="$LOG_DIR/.lock"

: "${LOOP_CODEX_CMD:=codex exec -}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  {
    echo "SKIPPED: scheduled loop already running"
    echo "repo=$REPO"
    echo "prompt_file=$PROMPT_FILE"
    echo "lock_dir=$LOCK_DIR"
  } | tee "$STDOUT_LOG"
  printf '{"run_id":"%s","status":"skipped_lock","repo":"%s","prompt_file":"%s"}\n' "$RUN_ID" "$REPO" "$PROMPT_FILE" > "$MANIFEST"
  exit 0
fi
trap 'rm -rf "$LOCK_DIR"' EXIT

printf '{"run_id":"%s","status":"started","repo":"%s","prompt_file":"%s","command":"%s"}\n' \
  "$RUN_ID" "$REPO" "$PROMPT_FILE" "$LOOP_CODEX_CMD" > "$MANIFEST"

if [[ "${LOOP_DRY_RUN:-0}" == "1" ]]; then
  {
    echo "DRY RUN: would execute scheduled loop"
    echo "repo=$REPO"
    echo "prompt_file=$PROMPT_FILE"
    echo "command=$LOOP_CODEX_CMD"
  } | tee "$STDOUT_LOG"
  printf '{"run_id":"%s","status":"dry_run","repo":"%s","prompt_file":"%s","command":"%s"}\n' \
    "$RUN_ID" "$REPO" "$PROMPT_FILE" "$LOOP_CODEX_CMD" > "$MANIFEST"
  exit 0
fi

set +e
# Cron is non-interactive; the configured command must read the prompt from stdin.
bash -lc "$LOOP_CODEX_CMD" < "$PROMPT_FILE" > "$STDOUT_LOG" 2> "$STDERR_LOG"
EXIT_CODE=$?
set -e

if [[ "$EXIT_CODE" -eq 0 ]]; then
  STATUS="success"
else
  STATUS="error"
fi

printf '{"run_id":"%s","status":"%s","exit_code":%s,"repo":"%s","prompt_file":"%s","command":"%s","stdout":"%s","stderr":"%s"}\n' \
  "$RUN_ID" "$STATUS" "$EXIT_CODE" "$REPO" "$PROMPT_FILE" "$LOOP_CODEX_CMD" "$STDOUT_LOG" "$STDERR_LOG" > "$MANIFEST"

exit "$EXIT_CODE"
