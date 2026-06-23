#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/skills/personaplex/scripts:${PYTHONPATH:-}"

python3 -m unittest discover -s skills/personaplex/tests -p 'test_p3_p5_live_websocket_memory_evidence_combined.py' -v

RUN_ROOT="/tmp/personaplex-p3-p5-combined-sanity"
OUT_JSON="/tmp/personaplex-p3-p5-combined-sanity-output.json"
rm -rf "$RUN_ROOT" "$OUT_JSON"

python3 skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py \
  --fixture skills/personaplex/fixtures/p3_p5_two_turn_fixture.json \
  --run-root "$RUN_ROOT" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
receipt = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert receipt["ok"] is True, receipt
assert receipt["turn_count"] >= 2, receipt
assert receipt["live_websocket"] is False, receipt
assert receipt["real_deepgram"] is False, receipt
assert receipt["real_gpu_personaplex"] is False, receipt
assert receipt["real_memory_upsert"] is False, receipt
assert receipt["real_create_evidence_case"] is False, receipt
assert receipt["sealed_turn_keys"] == ["conversation:p3p5-session:000002"], receipt["sealed_turn_keys"]
assert receipt["stale_rejection_count"] >= 1, receipt["stale_rejection_count"]
assert receipt["queue_depth_at_release"] == 0, receipt["queue_depth_at_release"]
assert receipt["memory_upsert_attempts"][0]["no_inline_vectors"] is True, receipt["memory_upsert_attempts"]
assert receipt["evidence_case_attempts"][-1]["fail_closed"] is True, receipt["evidence_case_attempts"]
print("p3-p5 combined sanity ok")
print(f"final_receipt={receipt['final_receipt_path']}")
PY
