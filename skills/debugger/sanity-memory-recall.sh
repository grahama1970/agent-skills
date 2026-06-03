#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

python scripts/recall_debugger_lessons.py \
  --query "route handler selected_handler mismatch" \
  --recall-json fixtures/memory/debugger-recall.json \
  --out "$tmp_dir/recall-advisory.json"

python - "$tmp_dir/recall-advisory.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
assert data["schema"] == "debugger.memory_recall.v1"
assert data["memory"]["found"] is True
assert data["lessons"][0]["advisory"] is True
assert data["safety"]["evidence_class"] == "memory_recall_advisory"
assert data["safety"]["fresh_debugger_proof"] is False
assert data["safety"]["can_satisfy_debugger_proof"] is False
assert data["safety"]["requires_new_breakpoint_proof_before_patch"] is True
PY

echo "SANITY PASS: debugger memory recall is advisory-only"
