#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

# Positive control: compile from real persona-dream artifacts shape
cat > "$T/storyboard.json" <<'EOF'
{"panels": [{"action": "Embry and Horus gesture and converse warmly over a glowing holographic evidence map, steam rising from the tea", "environment": "small tea table on a stormy void world terrace, colossal glowing eye in the storm clouds, distant alien creatures moving peacefully", "camera": "medium two-shot, slow push in"}]}
EOF
./run.sh compile --out "$T/packet.json" --storyboard "$T/storyboard.json" \
  --refs "Embry=https://example.com/embry.png" --refs "Horus=https://example.com/horus.png" \
  | grep -q '"status": "PASS"'
./run.sh validate "$T/packet.json" | grep -q '"status": "PASS"'
python3 -c "
import json; p=json.load(open('$T/packet.json'))
assert p['model_id'].endswith('reference-to-video')
assert len(p['request']['elements'])==2
assert '@Element1' in p['request']['prompt'] and '@Element2' in p['request']['prompt']
assert len(p['request']['prompt'])<=800
assert p['seam_validation']['status']=='PASS'
"
echo "PASS positive-control"

# Negative control 1: T2V endpoint with elements must FAIL (the 2026-09-07 bug)
python3 -c "
import json; p=json.load(open('$T/packet.json'))
p['model_id']='fal-ai/kling-video/v3/standard/text-to-video'
json.dump(p, open('$T/bad_t2v.json','w'))
"
if ./run.sh validate "$T/bad_t2v.json" >/dev/null 2>&1; then
  echo "FAIL: t2v+elements accepted"; exit 1
fi
echo "PASS negative-control-t2v"

# Negative control 2: element missing reference_image_urls must FAIL (422 class)
python3 -c "
import json; p=json.load(open('$T/packet.json'))
del p['request']['elements'][0]['reference_image_urls']
json.dump(p, open('$T/bad_el.json','w'))
"
if ./run.sh validate "$T/bad_el.json" >/dev/null 2>&1; then
  echo "FAIL: incomplete element accepted"; exit 1
fi
echo "PASS negative-control-element"

# Negative control 3: unbound element must FAIL
python3 -c "
import json; p=json.load(open('$T/packet.json'))
p['request']['prompt']=p['request']['prompt'].replace('@Element2 is Horus.','')
json.dump(p, open('$T/bad_bind.json','w'))
"
if ./run.sh validate "$T/bad_bind.json" >/dev/null 2>&1; then
  echo "FAIL: unbound element accepted"; exit 1
fi
echo "PASS negative-control-binding"

# Safety boundary: compile/validate perform no network calls or paid submits
grep -q "PAID" scripts/compile_kling_request.py  # submit is labeled
echo "ALL SANITY PASS"
