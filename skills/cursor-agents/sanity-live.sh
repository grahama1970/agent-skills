#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECEIPT="/tmp/cursor-agents-live-models-${STAMP}.json"

"$SCRIPT_DIR/run.sh" models --json --receipt "$RECEIPT" >/tmp/cursor-agents-live-models-${STAMP}.stdout.json
python3 - "$RECEIPT" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text())
if not receipt.get("ok"):
    raise SystemExit(f"live models check failed: {receipt}")
items = receipt.get("response", {}).get("items")
if not isinstance(items, list) or not items:
    raise SystemExit("live models check did not return a non-empty items list")
print(sys.argv[1])
PY
