#!/usr/bin/env bash
# Behavioral acceptance gates for best-practices-workflowscript.
# Positive control, negative control, safety boundary (linter never mutates the
# target), and artifact/schema assertions on the --json-out oracle.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d /tmp/bp-wfs-sanity.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
LINT="$HERE/scripts/validate-workflowscript.sh"
fail=0

# --- positive control: portable script passes and emits a CLEAN verdict
cat > "$WORK/good.workflow.js" <<'EOF'
const g=await runs.run('gate',{agent:'scout',task:'Compare against origin/main.',outputSchema:{type:'object',additionalProperties:false,properties:{ok:{type:'boolean'}},required:['ok']}});
return {ok:g.structuredOutput.ok};
EOF
"$LINT" "$WORK/good.workflow.js" --json-out "$WORK/good.json" > "$WORK/good.stdout" 2>&1
[[ $? -eq 0 ]] || { echo "FAIL positive-control: clean script exited nonzero"; cat "$WORK/good.stdout"; fail=1; }
python3 - "$WORK/good.json" <<'PY' || fail=1
import json,sys
d=json.load(open(sys.argv[1]))
assert d["verdict"]=="CLEAN", f"verdict {d['verdict']} != CLEAN"
assert d["violations"]==[], "clean script must have zero violations"
assert set(d) >= {"file","verdict","violations","advisories"}, "json oracle missing required keys"
PY

# --- negative control: injected anti-patterns fail closed with named rules
cat > "$WORK/bad.workflow.js" <<'EOF'
const g = async () => { return 1; };
async function helper(){ return runs.run('x',{}); }
const fs = require('fs');
EOF
"$LINT" "$WORK/bad.workflow.js" --json-out "$WORK/bad.json" > "$WORK/bad.stdout" 2>&1
rc=$?
[[ $rc -eq 1 ]] || { echo "FAIL negative-control: bad script exited $rc (want 1)"; fail=1; }
python3 - "$WORK/bad.json" <<'PY' || fail=1
import json,sys
d=json.load(open(sys.argv[1]))
assert d["verdict"]=="FAIL", f"verdict {d['verdict']} != FAIL"
rules={v["rule"] for v in d["violations"]}
assert {"arrow_function","nested_async_function","host_global_or_fs"} <= rules, f"missing rules: {rules}"
assert all(isinstance(v["line"],int) and v["line"]>=1 for v in d["violations"]), "violations need integer lines"
PY

# --- safety boundary: the linter must never modify the target file
before=$(sha256sum "$WORK/bad.workflow.js" | cut -d' ' -f1)
"$LINT" "$WORK/bad.workflow.js" > /dev/null 2>&1
after=$(sha256sum "$WORK/bad.workflow.js" | cut -d' ' -f1)
[[ "$before" == "$after" ]] || { echo "FAIL safety-boundary: linter mutated the target file"; fail=1; }

# --- noise control: empty/whitespace file is CLEAN, not a crash
printf '\n\n' > "$WORK/empty.workflow.js"
"$LINT" "$WORK/empty.workflow.js" > /dev/null 2>&1
[[ $? -eq 0 ]] || { echo "FAIL noise-control: empty file should be CLEAN"; fail=1; }

# --- usage error: missing file exits 2 with usage, not a crash
"$LINT" "$WORK/nonexistent.js" > /dev/null 2>&1
[[ $? -eq 2 ]] || { echo "FAIL usage-error: missing file should exit 2"; fail=1; }

if (( fail )); then echo "SANITY: FAIL"; exit 1; fi
echo "SANITY: PASS (positive, negative, safety-boundary, noise, usage gates)"
