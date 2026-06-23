#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
python -m unittest discover -s skills/personaplex/tests -v
RUN_ROOT="${TMPDIR:-/tmp}/personaplex-p0-harness-sanity"
rm -rf "$RUN_ROOT"
python skills/personaplex/scripts/personaplex_multiturn_probe.py \
  --fixture skills/personaplex/fixtures/p0_multiturn_interrupt.json \
  --run-root "$RUN_ROOT" \
  --json
python - "$RUN_ROOT/final-receipt.json" <<'PY'
import json, sys
path = sys.argv[1]
receipt = json.load(open(path, encoding="utf-8"))
assert receipt["ok"] is True, receipt
assert receipt["sealed_turn_keys"] == ["conversation:p0-session:000002"], receipt["sealed_turn_keys"]
assert receipt["stale_rejection_count"] >= 1, receipt["stale_rejection_count"]
assert receipt["release_receipts"][-1]["queue_depth_at_release"] == 0, receipt["release_receipts"]
assert receipt["session_head"]["latest_turn_id"] == 2, receipt["session_head"]
print("p0 harness sanity ok")
print(f"final_receipt={path}")
PY
