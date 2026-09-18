#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Positive control: a valid gated decision-tree spec must pass.
out=$(./run.sh check fixtures/good_decision_tree.json --json)
echo "$out" | python3 -c "import json,sys; v=json.load(sys.stdin); assert v['ok'] is True, v; assert v['errors']==[], v" \
  || { echo "FAIL: good_decision_tree.json should pass"; exit 1; }
echo "OK: good_decision_tree.json passes"

# Negative control: the star fan-out-for-sequence bug must be rejected with VIEW_TOPOLOGY_MISMATCH.
if ./run.sh check fixtures/bad_fanout_star.json --json > /tmp/bad_fanout_verdict.json 2>/dev/null; then
  echo "FAIL: bad_fanout_star.json should have been rejected"; exit 1
fi
python3 -c "
import json
v = json.load(open('/tmp/bad_fanout_verdict.json'))
assert v['ok'] is False, v
codes = {e['code'] for e in v['errors']}
assert 'VIEW_TOPOLOGY_MISMATCH' in codes, codes
"
echo "OK: bad_fanout_star.json rejected with VIEW_TOPOLOGY_MISMATCH"

# Negative control: labels overlapping arrows/boxes -- too-long label must be rejected.
if ./run.sh check fixtures/label_too_long.json --json > /tmp/label_verdict.json 2>/dev/null; then
  echo "FAIL: label_too_long.json should have been rejected"; exit 1
fi
python3 -c "
import json
v = json.load(open('/tmp/label_verdict.json'))
assert v['ok'] is False, v
codes = {e['code'] for e in v['errors']}
assert 'LABEL_TOO_LONG' in codes, codes
"
echo "OK: label_too_long.json rejected with LABEL_TOO_LONG"

# Advisory: straight routing on a flow edge warns but does not block by itself.
out=$(./run.sh check fixtures/routing_straight_warning.json --json)
echo "$out" | python3 -c "
import json, sys
v = json.load(sys.stdin)
assert v['ok'] is True, v
codes = {w['code'] for w in v['warnings']}
assert 'CONNECTOR_ROUTING_STRAIGHT' in codes, v
"
echo "OK: routing_straight_warning.json passes with advisory CONNECTOR_ROUTING_STRAIGHT warning"

# best-practices-python module hygiene.
python3 - <<'PY'
from pathlib import Path
p = Path('scripts/diagram_design_check.py')
text = p.read_text()
if len(text.splitlines()) > 800:
    raise SystemExit('diagram_design_check.py exceeds 800 lines')
if not text.startswith('#!/usr/bin/env python3\n"""'):
    raise SystemExit('module docstring missing')
for forbidden in ('import requests', 'shell=True', 'pickle', 'yaml.load(', 'argparse', 'import click'):
    if forbidden in text:
        raise SystemExit(f'forbidden token: {forbidden}')
print('PYTHON_STANDARDS_OK')
PY

echo "SANITY PASS"
