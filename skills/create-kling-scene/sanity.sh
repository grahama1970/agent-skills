#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
# positive control: valid tea scene table + existing ref files
cp ../best-practices-scene-script-writing/fixtures/scene_table_tea.json "$T/scene.json"
printf 'x' > "$T/embry.png"; printf 'x' > "$T/horus.png"
CHARS=$(python3 -c "import json; print(' '.join(e['element_id'].split('_',1)[-1] for e in json.load(open('$T/scene.json'))['elements'] if e['element_type']=='character'))")
REFS=(); for c in $CHARS; do REFS+=(--refs "$c=$T/$c.png"); printf 'x' > "$T/$c.png"; done
./run.sh build --scene "$T/scene.json" "${REFS[@]}" --out-dir "$T/run" >/dev/null
python3 -c "
import json; r=json.load(open('$T/run/receipt.json'))
assert r['status']=='PASS', r
assert json.load(open('$T/run/kling_request.json'))['request']['prompt']
assert 'submit' in r['next_command']
print('PASS positive-control build')"
# negative control: filler interaction blocks at stage 1 with triage code
python3 -c "
import json; t=json.load(open('$T/scene.json'))
t['elements'][0]['environment_interaction']='present'
json.dump(t,open('$T/bad.json','w'))"
if ./run.sh build --scene "$T/bad.json" "${REFS[@]}" --out-dir "$T/run2" >/dev/null 2>&1; then
  echo "FAIL: bad table accepted"; exit 1; fi
python3 -c "
import json; r=json.load(open('$T/run2/receipt.json'))
assert r['status']=='BLOCKED' and r['failed_stage']=='scene_table_gate', r
assert r['triage']['code']=='scene_table_interaction_filler', r['triage']
print('PASS negative-control scene gate + triage code')"
# negative control: missing reference blocks at stage 2
if ./run.sh build --scene "$T/scene.json" --refs nobody=$T/embry.png --out-dir "$T/run3" >/dev/null 2>&1; then
  echo "FAIL: missing character ref accepted"; exit 1; fi
python3 -c "
import json; r=json.load(open('$T/run3/receipt.json'))
assert r['failed_stage']=='reference_check', r
print('PASS negative-control reference check')"
# escalation control: unresolvable triage (minted code) -> interview questions + needs_attention
python3 - <<'PYEOF'
import json, sys
sys.path.insert(0, 'scripts')
from pathlib import Path
import create_kling_scene as cks
import tempfile, typer
T = Path(tempfile.mkdtemp())
receipt = {"schema": "create_kling_scene.receipt.v1", "stages": []}
try:
    cks._fail("reference_check", ["completely novel unresolvable failure zzqx-77"], receipt, T/"receipt.json")
except typer.Exit:
    pass
r = json.loads((T/"receipt.json").read_text())
assert r["needs_attention"][0]["reason"] == "triage_unresolvable", r
assert "interview" in r["needs_attention"][0]["resume_hint"], r
q = json.loads((T/"interview_questions.json").read_text())
assert q["questions"][0]["id"] == "repair_decision", q
assert r["seam_validation"]["status"] == "PASS"
print("PASS escalation-control interview handoff")
PYEOF
echo "ALL SANITY PASS"
