#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT
"$SCRIPT_DIR/run.sh" validate-qra "$SCRIPT_DIR/fixtures/sample_qra.json" >/dev/null
"$SCRIPT_DIR/run.sh" fixture "$SCRIPT_DIR/fixtures/sample_qra.json" --out "$OUT" >/dev/null
"$SCRIPT_DIR/run.sh" validate-advice "$OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$OUT" <<'PY'
import json, sys
packet = json.load(open(sys.argv[1], encoding="utf-8"))
assert packet["schema"] == "qra_grade_advice.v1"
assert packet["qra_id"] == "fixture-qra-001"
assert packet["lane_receipts"][0]["latency_seconds"] >= 0
assert packet["browser_advisor_decision"] in {"skip", "escalate", "calibration"}
assert isinstance(packet["best_practice_violations"], list)
PY
printf '{"schema":"qra_grade_advice.sanity_receipt.v1","status":"PASS","mocked":false,"live":["local filesystem","pydantic validators"],"does_not_prove":["live pool API","Pi subagent fanout","browser advisor execution"]}\n'
