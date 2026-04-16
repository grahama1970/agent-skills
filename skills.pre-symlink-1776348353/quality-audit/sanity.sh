#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [quality-audit] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh quality_audit.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: uv available
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "  uv available"

# Check 3: quality_audit.py is parseable
if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/quality_audit.py').read())" 2>/dev/null; then
    echo "  quality_audit.py parses without errors"
else
    echo "FAIL: quality_audit.py has syntax errors"
    exit 1
fi

# Check 4: Core Python imports (stdlib - always available)
if python3 -c "
import json, random, sys, math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
" 2>/dev/null; then
    echo "  Python stdlib imports OK"
else
    echo "FAIL: Python stdlib imports failed"
    exit 1
fi

# Check 5: Optional scipy (gracefully handled)
if python3 -c "from scipy import stats" 2>/dev/null; then
    echo "  scipy available (chi-square tests enabled)"
else
    echo "  INFO: scipy not installed (chi-square tests will be unavailable, but skill handles this)"
fi

# Check 6: Smoke test - load_input with inline JSONL
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

cat > "$TMPDIR/test.jsonl" << 'JSONL'
{"id": "T1", "input": {"name": "Test1"}, "output": {"tag": "A"}, "metadata": {"framework": "alpha"}}
{"id": "T2", "input": {"name": "Test2"}, "output": {"tag": "B"}, "metadata": {"framework": "alpha"}}
{"id": "T3", "input": {"name": "Test3"}, "output": {"tag": "C"}, "metadata": {"framework": "beta"}}
{"id": "T4", "input": {"name": "Test4"}, "output": {"tag": "D"}, "metadata": {"framework": "beta"}}
{"id": "T5", "input": {"name": "Test5"}, "output": {"tag": "E"}, "metadata": {"framework": "alpha"}}
{"id": "T6", "input": {"name": "Test6"}, "output": {"tag": "F"}, "metadata": {"framework": "beta"}}
JSONL

if python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from quality_audit import load_input
data = load_input('$TMPDIR/test.jsonl')
assert len(data) == 6, f'Expected 6 records, got {len(data)}'
print('  Loaded 6 records from test JSONL')
" 2>&1; then
    : # output printed by python
else
    echo "FAIL: load_input function failed on test data"
    exit 1
fi

echo "Result: PASS"
