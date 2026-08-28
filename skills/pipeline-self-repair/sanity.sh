#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/pipeline-self-repair-uv-env}"
uv run --project . pytest tests -q
TMP="$(mktemp -d /tmp/pipeline-self-repair-sanity.XXXXXX)"
./run.sh record-failure \
  --pipeline persona-dream \
  --step-id phase_11_kling_submit \
  --run-id sanity-run \
  --raw-signal "multi_prompt prompt exceeds 512 characters" \
  --layer kling \
  --target skills/persona-dream \
  --run-root "$TMP" \
  --ledger "$TMP/replay_ledger.jsonl" \
  --skip-memory \
  --skip-github \
  --no-ticket \
  --json > "$TMP/record.json"
./run.sh inspect --ledger "$TMP/replay_ledger.jsonl" --json > "$TMP/inspect.json"
python - <<'PY' "$TMP/record.json" "$TMP/inspect.json"
import json, sys
record=json.load(open(sys.argv[1]))
inspect=json.load(open(sys.argv[2]))
assert record["status"] in {"RECORDED_REPAIR_REQUIRED", "RECORDED_NEEDS_TRIAGE"}, record
assert inspect["event_count"] >= 1, inspect
assert inspect["open_failure_count"] == 1, inspect
print("PIPELINE_SELF_REPAIR_SANITY_OK")
PY
