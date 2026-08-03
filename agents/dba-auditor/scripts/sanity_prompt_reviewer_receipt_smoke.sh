#!/usr/bin/env bash
set -euo pipefail

ROOT="${AGENT_SKILLS_ROOT:-/home/graham/workspace/experiments/agent-skills}"
SCRIPT="$ROOT/agents/dba-auditor/scripts/prompt_reviewer_receipt.py"
WORK_DIR="${1:-${TMPDIR:-/tmp}/dewey-prompt-reviewer-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$WORK_DIR"

python3 "$SCRIPT" make-request \
  --out-dir "$WORK_DIR" \
  --request-id "dewey-prompt-reviewer-standalone-smoke" \
  --failed-dimension qra_coverage_per_control \
  --qra-missing-count 4883 \
  --model-pool "${DEWEY_QRA_MODEL_POOL:-qra-deepseek-pool}" \
  > "$WORK_DIR/make-request.json"

REQUEST_JSON="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_json"])' "$WORK_DIR/make-request.json")"
REQUEST_MD="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_markdown"])' "$WORK_DIR/make-request.json")"
RECEIPT_JSON="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["receipt_json"])' "$WORK_DIR/make-request.json")"

python3 "$SCRIPT" command \
  --request-markdown "$REQUEST_MD" \
  --request-json "$REQUEST_JSON" \
  --receipt-json "$RECEIPT_JSON" \
  --json > "$WORK_DIR/prompt-reviewer-command.json"

if [[ "${DEWEY_PROMPT_REVIEWER_SMOKE_RUN:-0}" == "1" ]]; then
  CMD_JSON="$WORK_DIR/prompt-reviewer-command.json"
  python3 - "$CMD_JSON" <<'PY'
import json, subprocess, sys
cmd = json.load(open(sys.argv[1]))["command"]
raise SystemExit(subprocess.call(cmd))
PY
  python3 "$SCRIPT" validate --request "$REQUEST_JSON" --receipt "$RECEIPT_JSON" --json > "$WORK_DIR/validation.json"
else
  python3 "$SCRIPT" sample-pass --request "$REQUEST_JSON" --out "$WORK_DIR/mock-pass-receipt.json" >/dev/null
  python3 "$SCRIPT" validate --request "$REQUEST_JSON" --receipt "$WORK_DIR/mock-pass-receipt.json" --allow-mock --json > "$WORK_DIR/validation.json"
fi

cat <<EOF
prompt_reviewer_receipt_smoke_dir=$WORK_DIR
request_json=$REQUEST_JSON
request_markdown=$REQUEST_MD
receipt_json=$RECEIPT_JSON
command_json=$WORK_DIR/prompt-reviewer-command.json
validation_json=$WORK_DIR/validation.json
EOF
