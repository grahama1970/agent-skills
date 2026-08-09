#!/usr/bin/env bash
# Cheap local proof: README parses and drift check runs (no live probes,
# no mutation). Exit 0 = parser healthy and site content matches README.
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$skill_dir"
./run.sh audit --no-live --json >/dev/null
echo "monitor-website sanity: OK (README parsed, no drift, no live probes)"

# #1298 voice canary + #1337 design-world contract
python3 "$skill_dir/../../site/scripts/copy_audit.py" >/dev/null
production_design_world="$("$skill_dir/run.sh" design-world-check --json)"
printf '%s' "$production_design_world" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["gates"]["distinctiveness_blind"]["status"] == "NOT_TESTED"'

valid_receipt="$skill_dir/fixtures/design-world/distinctiveness/valid-distinctiveness-receipt.json"
valid_design_world="$("$skill_dir/run.sh" design-world-check --json --distinctiveness-receipt "$valid_receipt")"
printf '%s' "$valid_design_world" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["gates"]["distinctiveness_blind"]["status"] == "PASS"'

invalid_receipt="$skill_dir/fixtures/design-world/distinctiveness/invalid-too-few-raters.json"
if "$skill_dir/run.sh" design-world-check --json --distinctiveness-receipt "$invalid_receipt" >/tmp/monitor-website-invalid-distinctiveness.json 2>&1; then
  echo "ERROR: invalid distinctiveness receipt unexpectedly passed" >&2
  exit 1
fi
python3 -c 'import json; data=json.load(open("/tmp/monitor-website-invalid-distinctiveness.json")); assert data["gates"]["distinctiveness_blind"]["status"] == "FAIL"'
