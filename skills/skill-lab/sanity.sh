#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [skill-lab] Sanity Check ==="

echo -n "Check 1 - SKILL.md exists: "
[[ -f "$SCRIPT_DIR/SKILL.md" ]] && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 2 - run.sh exists: "
[[ -x "$SCRIPT_DIR/run.sh" ]] && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 3 - Core scripts exist: "
for s in scan_soup.py gap_detector.py scaffolder.py composer.py bond_predictor.py bond_teacher.py bond_harvest.py; do
    if [[ ! -f "$SCRIPT_DIR/scripts/$s" ]]; then
        echo "FAIL: missing scripts/$s"
        exit 1
    fi
done
echo "PASS"

echo -n "Check 4 - Scan soup runs: "
python3 "$SCRIPT_DIR/scripts/scan_soup.py" --skills-root "$(dirname "$SCRIPT_DIR")" --json > /dev/null 2>&1 && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 5 - Gap detector runs: "
python3 "$SCRIPT_DIR/scripts/gap_detector.py" --task "test task" --skills-root "$(dirname "$SCRIPT_DIR")" --json > /dev/null 2>&1 && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 6 - Composer elegance runs: "
"$SCRIPT_DIR/run.sh" run --task "extract PDF" --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0)" && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 7 - Attractors command runs: "
"$SCRIPT_DIR/run.sh" attractors --json 2>/dev/null | python3 -c "import sys,json; json.load(sys.stdin); sys.exit(0)" && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 8 - Granularity command runs: "
"$SCRIPT_DIR/run.sh" granularity --json 2>/dev/null | python3 -c "import sys,json; json.load(sys.stdin); sys.exit(0)" && echo "PASS" || { echo "FAIL"; exit 1; }

# --- /memory integration checks ---

echo -n "Check 9 - Memory helper imports: "
cd "$SCRIPT_DIR/scripts"
python3 -c "
from scan_soup import _memory_learn, _memory_recall, _data_hash, register_in_memory
from bond_predictor import sync_bonds_to_memory
from gap_detector import _recall_skills_for_task, detect_gaps
from composer import _recall_known_composition, _store_successful_chain
from bond_harvest import _sync_attractors_to_memory
print('OK')
" > /dev/null 2>&1 && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 10 - _memory_learn uses --tag not --tags in code: "
python3 -c "
import ast, inspect, textwrap
from scan_soup import _memory_learn
src = inspect.getsource(_memory_learn)
# Check actual code lines (not docstrings) for broken --tags usage
tree = ast.parse(textwrap.dedent(src))
# Verify cmd.extend calls use '--tag' not '--tags'
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and node.value == '--tags':
        raise AssertionError('BROKEN: code uses --tags (plural) as string literal')
print('OK')
" > /dev/null 2>&1 && echo "PASS" || { echo "FAIL: _memory_learn uses broken --tags syntax"; exit 1; }

echo -n "Check 11 - register_in_memory 3-pass structure: "
python3 -c "
import inspect
from scan_soup import register_in_memory
src = inspect.getsource(register_in_memory)
assert 'Pass 1' in src or 'reg_skills' in src, 'Missing skill registration pass'
assert 'Pass 2' in src or 'reg_caps' in src, 'Missing capability registration pass'
assert 'Pass 3' in src or 'reg_edges' in src, 'Missing edge registration pass'
print('OK')
" > /dev/null 2>&1 && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 12 - gap_detector returns memory_hints field: "
python3 -c "
import json, sys
sys.path.insert(0, '.')
from scan_soup import scan_soup
from pathlib import Path
graph = scan_soup(Path('..').resolve().parent)
from gap_detector import detect_gaps
result = detect_gaps('extract tables from PDF', graph)
assert 'memory_hints' in result, 'memory_hints field missing from detect_gaps output'
assert isinstance(result['memory_hints'], int), 'memory_hints must be int'
print('OK')
" > /dev/null 2>&1 && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "Check 13 - scan_soup --register runs: "
SKILLS_ROOT="$(dirname "$SCRIPT_DIR")"
if [[ -x "$SKILLS_ROOT/memory/run.sh" ]]; then
    python3 "$SCRIPT_DIR/scripts/scan_soup.py" --skills-root "$SKILLS_ROOT" --register 2>&1 | grep -q "Registered" && echo "PASS" || { echo "FAIL"; exit 1; }
else
    echo "SKIPPED (no /memory skill)"
fi

echo -n "Check 14 - sync_bonds_to_memory callable: "
python3 -c "
from bond_predictor import sync_bonds_to_memory
result = sync_bonds_to_memory(top_n=5)
assert isinstance(result, int), 'sync_bonds_to_memory must return int'
print('OK')
" > /dev/null 2>&1 && echo "PASS" || { echo "FAIL"; exit 1; }

echo ""
echo "Result: PASS"
