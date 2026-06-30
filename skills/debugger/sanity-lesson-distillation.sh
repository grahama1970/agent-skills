#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

python scripts/distill_debugger_lesson.py \
  fixtures/proofs/canonical-valid.json \
  --out "$tmp_dir/canonical.lesson.json"

python scripts/distill_debugger_lesson.py \
  fixtures/proofs/contains-secrets-valid.json \
  --out "$tmp_dir/redacted.lesson.json"

python - "$tmp_dir/redacted.lesson.json" <<'PY'
import json
import sys
from pathlib import Path

lesson = json.loads(Path(sys.argv[1]).read_text())
text = json.dumps(lesson, sort_keys=True)
for forbidden in [
    "sk-test-secret-1234567890",
    "Bearer abc.def.ghi",
    "Bearer abcdef1234567890",
    "${HOME}/workspace/private/app.py",
]:
    if forbidden in text:
        raise SystemExit(f"distilled lesson leaked forbidden value: {forbidden}")

assert lesson["schema"] == "debugger.lesson.v1"
assert lesson["memory_safety"]["raw_locals_stored"] is False
assert lesson["memory_safety"]["can_satisfy_debugger_proof"] is False
local_names = {item["name"] for item in lesson["runtime_state"]["captures"]["locals"]}
assert {"api_key", "client", "route"}.issubset(local_names)
PY

echo "SANITY PASS: debugger lesson distillation redacts raw paused state"
