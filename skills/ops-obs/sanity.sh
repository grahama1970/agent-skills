#!/usr/bin/env bash
# Behavioral acceptance gates for ops-obs (positive, negative, adversarial, schema).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail_() { echo "SANITY FAIL: $1" >&2; exit 1; }

# positive control: CLI wiring
"$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1 || fail_ "run.sh --help exited nonzero"

# behavioral positive: doctor emits valid JSON with the required structure
"$SCRIPT_DIR/run.sh" doctor | uv run --project "$SCRIPT_DIR" python -c \
  'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d["ok"] and d["checks"] else 1)' \
  || fail_ "doctor did not emit ok:true with checks[]"

# behavioral positive: streamdeck bindings carry the schema id and runnable commands
"$SCRIPT_DIR/run.sh" streamdeck bindings | uv run --project "$SCRIPT_DIR" python -c \
  'import json,sys,shlex; d=json.load(sys.stdin); raise SystemExit(0 if d["schema"]=="ops-obs.streamdeck_bindings.v1" and all(shlex.split(b["command"])[0].startswith("/") for b in d["buttons"]) else 1)' \
  || fail_ "streamdeck bindings missing schema id or runnable commands"

# negative control: missing required argument must exit 2 (usage)
set +e
"$SCRIPT_DIR/run.sh" scene set >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] || fail_ "scene set without argument exited $rc, expected 2"

# adversarial: closed port must produce the typed envelope, exit 1, no traceback
set +e
out=$("$SCRIPT_DIR/run.sh" status --host 127.0.0.1 --port 1 --timeout 3 2>/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] || fail_ "status against closed port exited $rc, expected 1"
echo "$out" | grep -q "obs_ws_connection_refused" || fail_ "typed code obs_ws_connection_refused missing"
echo "$out" | grep -q "next_command" || fail_ "next_command missing from failure envelope"
echo "$out" | grep -q '"triage"' || fail_ "triage classification block missing from failure envelope"
if echo "$out" | grep -q "Traceback"; then fail_ "traceback leaked to stdout"; fi

# adversarial: notify through the ops-herdr bridge to an unknown tab fails typed
set +e
out=$("$SCRIPT_DIR/run.sh" notify probe --tab "__no_such_tab__" 2>/dev/null)
rc=$?
set -e
[ "$rc" -eq 1 ] || fail_ "notify unknown tab exited $rc, expected 1"
echo "$out" | grep -q "obs_notify" || fail_ "typed obs_notify code missing"
if echo "$out" | grep -q "Traceback"; then fail_ "traceback leaked to stdout (notify)"; fi

# schema/artifact gate: protocol auth vector regression
"$SCRIPT_DIR/run.sh" selftest | grep -q "DH8rJzw8w3csbWfcnTbO18+zOu0c+LSevHghwA2BbW0=" \
  || fail_ "auth vector mismatch (protocol regression)"

# fixture loads as JSON
uv run --project "$SCRIPT_DIR" python -c \
  'import json; json.load(open("'"$SCRIPT_DIR"'/fixtures/agentic_eval.json"))' \
  || fail_ "fixtures/agentic_eval.json is not valid JSON"

echo "sanity: all gates passed"
