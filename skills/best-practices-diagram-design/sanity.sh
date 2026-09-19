#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

check_codes() {
  local fixture=$1 expected_ok=$2 expected_codes=$3 out
  out=$(mktemp)
  if ./run.sh check "fixtures/$fixture" --json >"$out" 2>/dev/null; then rc=0; else rc=$?; fi
  python3 - "$out" "$expected_ok" "$expected_codes" "$rc" <<'PY'
import json,sys
path, expected_ok, expected_codes, rc = sys.argv[1:]
v=json.load(open(path))
want_ok=expected_ok == 'true'
assert v['ok'] is want_ok, v
assert (int(rc)==0) is want_ok, (rc,v)
codes={e['code'] for e in v['errors']}
for code in filter(None, expected_codes.split(',')):
    assert code in codes, (code,codes)
PY
  rm -f "$out"
  echo "OK: $fixture => $expected_codes"
}

check_geometry() {
  local fixture=$1 expected_ok=$2 expected_codes=$3 out
  out=$(mktemp)
  if ./run.sh geometry "fixtures/$fixture" --json >"$out" 2>/dev/null; then rc=0; else rc=$?; fi
  python3 - "$out" "$expected_ok" "$expected_codes" "$rc" <<'PY'
import json,sys
path, expected_ok, expected_codes, rc = sys.argv[1:]
v=json.load(open(path))
want_ok=expected_ok == 'true'
assert v['ok'] is want_ok, v
assert (int(rc)==0) is want_ok, (rc,v)
codes={e['code'] for e in v['errors']}
for code in filter(None, expected_codes.split(',')):
    assert code in codes, (code,codes)
PY
  rm -f "$out"
  echo "OK: $fixture => ${expected_codes:-PASS}"
}

check_codes good_decision_tree.json true ""
check_codes bad_fanout_star.json false PRECONDITION_BYPASS
check_codes bad_fanout_star_extra_gate.json false PRECONDITION_BYPASS
check_codes bypass_direct_tier3.json false PRECONDITION_BYPASS
check_codes branch_label_swap.json false BRANCH_LABEL_MISMATCH
# Independent fanout is semantically valid; only the create-svg adapter ceiling rejects five targets.
check_codes fanout_5_targets.json false FANOUT_TOO_MANY

check_geometry geometry_straight_clean.svg true ""
check_geometry geometry_node_overlap.svg false NODE_OVERLAP
check_geometry geometry_edge_node_cross.svg false EDGE_NODE_INTERSECTION,EDGE_TEXT_INTERSECTION
check_geometry geometry_diamond_overflow.svg false TEXT_OUTSIDE_CONTAINER

python3 - <<'PY'
import ast, json
from pathlib import Path
for path in ('scripts/diagram_design_check.py', 'scripts/diagram_geometry_check.py'):
    text=Path(path).read_text()
    ast.parse(text)
    assert len(text.splitlines()) <= 800, path
    assert text.startswith('#!/usr/bin/env python3\n"""'), path
    for forbidden in ('import requests', 'shell=True', 'pickle', 'yaml.load(', 'argparse', 'import click'):
        assert forbidden not in text, (path, forbidden)
json.loads(Path('fixtures/agentic_eval.json').read_text())
print('PYTHON_AND_JSON_STANDARDS_OK')
PY

python3 - <<'PY'
from pathlib import Path
import yaml
text=Path('SKILL.md').read_text()
front=text.split('---',2)[1]
data=yaml.safe_load(front)
for key in ('name','description','triggers','provides','composes','complies'):
    assert data.get(key), key
print('FRONTMATTER_OK')
PY

echo "SANITY PASS"
