#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "=== [ops-chatterbox] Sanity Check ==="

for f in SKILL.md run.sh sanity.sh pyproject.toml scripts/diagnose.py fixtures/agentic_eval.json; do
  if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
    echo "FAIL missing $f"
    exit 1
  fi
done

python3 -m py_compile "$SCRIPT_DIR/scripts/diagnose.py"

"$SCRIPT_DIR/run.sh" health --url http://127.0.0.1:9/health --timeout 0.2 --json > "$tmpdir/health.json"
python3 - "$tmpdir/health.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["schema"] == "ops_chatterbox.health_receipt.v1"
assert data["status"] == "NEEDS_ATTENTION"
assert data["live"] is True
assert data["mocked"] is False
assert data["failures"]
PY

cat > "$tmpdir/bad_chatterbox_call.py" <<'PY'
payload = {"answer_text": "[laugh] hello", "voice_delivery": {"chatterbox_tags": ["[laugh]"]}}
audio = response["finished_response_audio"]
if response["tag_handling"]["tags_interpreted"]:
    print("worked")
PY
"$SCRIPT_DIR/run.sh" assess "$tmpdir/bad_chatterbox_call.py" --json > "$tmpdir/assess.json"
python3 - "$tmpdir/assess.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["schema"] == "ops_chatterbox.assess_receipt.v1"
assert data["status"] == "NEEDS_ATTENTION"
assert data["issues"]
PY

"$SCRIPT_DIR/run.sh" render-smoke --text "sanity" --json > "$tmpdir/render_blocked.json"
python3 - "$tmpdir/render_blocked.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
assert data["status"] == "BLOCKED_LIVE_FLAG_REQUIRED"
assert data["live"] is False
PY

echo "Result: PASS"
