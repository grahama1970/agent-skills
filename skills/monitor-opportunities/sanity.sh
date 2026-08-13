#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="${TMPDIR:-/tmp}/monitor-opportunities-sanity"
rm -rf "$OUT_DIR"

cd "$REPO_ROOT"
uv run --project "$SCRIPT_DIR" --extra test pytest "$SCRIPT_DIR/tests" -q
"$SCRIPT_DIR/run.sh" status --json >/dev/null
"$SCRIPT_DIR/run.sh" verify --out "$OUT_DIR" >/dev/null
python3 - "$OUT_DIR/verification-receipt.json" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert receipt["overall"] == "PASS", receipt
assert receipt["network_used"] is False, receipt
assert receipt["external_effects"] is False, receipt
print("monitor-opportunities sanity: PASS")
PY
