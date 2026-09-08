#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
# positive control: valid tea scene table + existing ref files
cp ../best-practices-scene-script-writing/fixtures/scene_table_tea.json "$T/scene.json"
python3 -c "
import zlib, struct, wave, sys
def png(p):
    raw = b'\\x89PNG\\r\\n\\x1a\\n'
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 0, 0, 0, 0))
    row = b'\\x00' + b'\\x80' * 64
    idat = chunk(b'IDAT', zlib.compress(row * 64, 0))
    open(p, 'wb').write(raw + ihdr + idat + chunk(b'IEND', b''))
def wav(p, secs):
    with wave.open(p, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b'\\x00\\x00' * int(8000 * secs))
png('$T/embry.png'); png('$T/horus.png')
wav('$T/embry.wav', 6); wav('$T/short.wav', 0.5)
"
CHARS=$(python3 -c "import json; print(' '.join(e['element_id'].split('_',1)[-1] for e in json.load(open('$T/scene.json'))['elements'] if e['element_type']=='character'))")
REFS=(); for c in $CHARS; do REFS+=(--refs "$c=$T/$c.png"); cp "$T/embry.png" "$T/$c.png" 2>/dev/null || true; done
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
# negative control: fake PNG (text bytes) rejected at media gate
printf 'not an image, definitely large enough? no' > "$T/fake.png"
if ./run.sh build --scene "$T/scene.json" --refs embry=$T/fake.png --refs horus=$T/horus.png --out-dir "$T/run4" >/dev/null 2>&1; then
  echo "FAIL: fake png accepted"; exit 1; fi
python3 -c "
import json; r=json.load(open('$T/run4/receipt.json'))
assert r['failed_stage']=='reference_check', r
assert any('magic bytes' in str(e) for e in r['errors']), r['errors']
print('PASS negative-control fake image rejected')"
# negative control: 0.5s wav outside lipsync bounds
if ./run.sh build --scene "$T/scene.json" "${REFS[@]}" --voice embry=$T/short.wav --out-dir "$T/run5" >/dev/null 2>&1; then
  echo "FAIL: short wav accepted"; exit 1; fi
python3 -c "
import json; r=json.load(open('$T/run5/receipt.json'))
assert any('bounds' in str(e) for e in r['errors']), r['errors']
print('PASS negative-control short wav rejected')"
# positive: valid wav accepted + typed instructions artifact emitted
./run.sh build --scene "$T/scene.json" "${REFS[@]}" --voice embry=$T/embry.wav --out-dir "$T/run6" >/dev/null
python3 -c "
import json; i=json.load(open('$T/run6/kling_instructions.json'))
assert i['schema']=='create_kling_scene.instructions.v1', i
assert i['voices'][0]['duration_s']==6.0, i['voices']
assert json.load(open('$T/run6/receipt.json'))['status']=='PASS'
print('PASS positive-control voice wav + instructions artifact')"
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
# binding-swap control: CLI refs in REVERSED character order must still bind positionally
python3 -c "
import json
chars=[e['element_id'] for e in json.load(open('$T/scene.json'))['elements'] if e['element_type']=='character']
print(len(chars))" > /dev/null
REV=(); for c in $(echo $CHARS | tr ' ' '\n' | tac); do REV+=(--refs "$c=$T/$c.png"); done
./run.sh build --scene "$T/scene.json" "${REV[@]}" --out-dir "$T/run7" >/dev/null
python3 -c "
import json
i=json.load(open('$T/run7/kling_instructions.json'))
chars=[e['element_id'] for e in json.load(open('$T/scene.json'))['elements'] if e['element_type']=='character']
for n,(c,r) in enumerate(zip(i['characters'], i['references']),1):
    assert c==r['name'] or c.endswith('_'+r['name']) or c.split('_',1)[-1]==r['name'], (n,c,r['name'])
print('PASS binding-order-control (reversed CLI order rebinds positionally)')"
# voice consumption: audio_plan.json must exist when a voice was validated
python3 -c "
import json; a=json.load(open('$T/run6/audio_plan.json'))
assert a['voices'][0]['name']=='embry' and a['next_stage'], a
print('PASS voice-consumption audio_plan emitted')"
echo "ALL SANITY PASS"
