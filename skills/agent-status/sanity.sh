#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo '{"ok":true}' >"$tmp/proof.json"

./run.sh init --campaign demo --goal "Demo status" --status-dir "$tmp/status"
./run.sh gate-passed --campaign demo --status-dir "$tmp/status" \
  --label "Demo gate" --verdict PASS_SPEC --proof "$tmp/proof.json" \
  --not-proven "Full goal not proven"
./run.sh artifact-add --campaign demo --status-dir "$tmp/status" \
  --path "$tmp/proof.json" --kind proof --label "Demo proof artifact"
./run.sh validate --campaign demo --status-dir "$tmp/status" >/dev/null
test -s "$tmp/status/STATUS.html"
grep -q '"artifacts"' "$tmp/status/status.json"

python3 - <<PY "$tmp/status/status.json"
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
status = json.loads(path.read_text())
status["state"] = "done"
path.write_text(json.dumps(status, indent=2) + "\n")
PY
if ./run.sh validate --campaign demo --status-dir "$tmp/status" >/dev/null 2>&1; then
  echo "FAIL: validate should reject state=done while not_proven is non-empty" >&2
  exit 1
fi

./run.sh --help >/dev/null

export PYTHONPATH="${PWD}/scripts${PYTHONPATH:+:$PYTHONPATH}"
if command -v uv >/dev/null 2>&1; then
  uv run pytest tests/ -q
else
  python3 -m pytest tests/ -q 2>/dev/null || python3 -m unittest discover -s tests -v
fi

echo "agent-status sanity passed"
