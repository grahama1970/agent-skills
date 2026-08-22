#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "=== [ops-realtimestt] Sanity Check ==="

for f in SKILL.md run.sh sanity.sh pyproject.toml scripts/diagnose.py fixtures/agentic_eval.json; do
  if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
    echo "FAIL missing $f"
    exit 1
  fi
done

python3 -m py_compile "$SCRIPT_DIR/scripts/diagnose.py"

"$SCRIPT_DIR/run.sh" health --url http://127.0.0.1:9 --timeout 0.2 --json > "$tmpdir/health.json"
python3 - "$tmpdir/health.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["schema"] == "ops_realtimestt.health_receipt.v1"
assert data["status"] == "NEEDS_ATTENTION"
assert data["live"] is True
assert data["mocked"] is False
assert data["failures"]
PY

cat > "$tmpdir/bad_stt_call.py" <<'PY'
models = requests.get("http://127.0.0.1:9000/v1/models")
speaker = transcript_text
memory.recall(user=speaker)
if requests.get("http://listener/health").ok:
    print("ready")
PY
"$SCRIPT_DIR/run.sh" assess "$tmpdir/bad_stt_call.py" --json > "$tmpdir/assess.json"
python3 - "$tmpdir/assess.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["schema"] == "ops_realtimestt.assess_receipt.v1"
assert data["status"] == "NEEDS_ATTENTION"
assert data["issues"]
PY

"$SCRIPT_DIR/run.sh" transcribe-smoke --audio "$tmpdir/missing.wav" --json > "$tmpdir/transcribe_blocked.json"
python3 - "$tmpdir/transcribe_blocked.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["status"] == "BLOCKED_LIVE_FLAG_REQUIRED"
assert data["live"] is False
PY

echo "Result: PASS"
