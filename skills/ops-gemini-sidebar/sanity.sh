#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN_FILE="$(mktemp)"
PROMPT_FILE="$(mktemp)"
trap 'rm -f "$PLAN_FILE" "$PROMPT_FILE"' EXIT

printf 'hello gemini\n' > "$PROMPT_FILE"

"$SCRIPT_DIR/run.sh" plan \
  --composer-x 10 --composer-y 20 \
  --send-x 30 --send-y 40 \
  --copy-x 50 --copy-y 60 \
  --out "$PLAN_FILE" --json >/tmp/ops-gemini-sidebar-plan.json

"$SCRIPT_DIR/run.sh" self-test --json >/tmp/ops-gemini-sidebar-self-test.json
"$SCRIPT_DIR/run.sh" submit --prompt-file "$PROMPT_FILE" --coords "$PLAN_FILE" --json >/tmp/ops-gemini-sidebar-submit-dry.json
"$SCRIPT_DIR/run.sh" copy-response --coords "$PLAN_FILE" --out /tmp/ops-gemini-sidebar-response.txt --json >/tmp/ops-gemini-sidebar-copy-dry.json

python3 - <<'PY'
import json
from pathlib import Path
checks = [
    ('/tmp/ops-gemini-sidebar-plan.json', 'ops_gemini_sidebar.coordinate_plan.v1', None),
    ('/tmp/ops-gemini-sidebar-self-test.json', 'ops_gemini_sidebar.command_receipt.v1', 'PASS'),
    ('/tmp/ops-gemini-sidebar-submit-dry.json', 'ops_gemini_sidebar.command_receipt.v1', 'DRY_RUN'),
    ('/tmp/ops-gemini-sidebar-copy-dry.json', 'ops_gemini_sidebar.command_receipt.v1', 'DRY_RUN'),
]
for path, schema, status in checks:
    data = json.loads(Path(path).read_text())
    if data.get('schema') != schema:
        raise SystemExit(f'{path}: schema mismatch {data.get("schema")}')
    if status and data.get('status') != status:
        raise SystemExit(f'{path}: status mismatch {data.get("status")}')
print('OPS_GEMINI_SIDEBAR_SANITY_PASS')
PY
