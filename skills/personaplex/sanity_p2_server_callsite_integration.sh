#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/skills/personaplex/scripts:$ROOT/skills/personaplex/scripts/_p2_compat:${PYTHONPATH:-}"

python3 -m unittest discover -s skills/personaplex/tests -p 'test_p2_server_callsite_integration.py' -v

RUN_ROOT="/tmp/personaplex-p2-server-callsite-sanity"
OUT_JSON="/tmp/personaplex-p2-server-callsite-sanity-output.json"
rm -rf "$RUN_ROOT" "$OUT_JSON"

python3 skills/personaplex/scripts/personaplex_p2_server_callsite_probe.py \
  --fixture skills/personaplex/fixtures/p2_server_callsite_two_turn_probe.json \
  --run-root "$RUN_ROOT" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
receipt = json.loads(path.read_text())
assert receipt["ok"] is True, receipt
assert receipt["p2_callsite_used_p1_controller"] is True, receipt
assert receipt["sealed_turn_keys"] == ["conversation:p2-session:000002"], receipt["sealed_turn_keys"]
assert receipt["stale_rejection_count"] >= 1, receipt["stale_rejection_count"]
assert receipt["release_receipts"], receipt
assert all(r["queue_depth_at_release"] == 0 for r in receipt["release_receipts"]), receipt["release_receipts"]
assert receipt["p2_speech_final_receipts"], receipt
assert any(item["status"] == "sealed" for item in receipt["p2_speech_final_receipts"]), receipt["p2_speech_final_receipts"]
assert any(item["status"] == "stale_fenced" for item in receipt["p2_speech_final_receipts"]), receipt["p2_speech_final_receipts"]
print("p2 server callsite integration sanity ok")
print(f"final_receipt={receipt['final_receipt_path']}")
PY
