#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [formalize-request] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md formalize.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: Python syntax check
echo -n "Check 2 - Python syntax: "
if python3 -m py_compile "$SCRIPT_DIR/formalize.py" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: syntax error in formalize.py"
    exit 1
fi

# Check 3: typer import (main CLI dependency)
echo -n "Check 3 - typer import: "
if python3 -c "import typer" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: typer not installed (pip install typer)"
    exit 1
fi

# Check 4: Core imports from formalize.py
echo -n "Check 4 - Core imports: "
python3 -c "
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import typer
print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 5: Smoke test - ambiguity detection (pure logic, no external deps)
echo -n "Check 5 - Ambiguity detection smoke test: "
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from formalize import detect_ambiguities, classify_spec_type, SpecType

# Test with ambiguous input
ambs = detect_ambiguities('How does this help with security?')
assert len(ambs) > 0, 'Expected ambiguities for vague input'

# Test with precise input (entity-anchored)
ambs2 = detect_ambiguities('How does CM-0049 mitigate T1422?')
assert len(ambs2) == 0, f'Expected no ambiguities for precise input, got {len(ambs2)}'

# Test spec type classification
assert classify_spec_type('prove that sum equals n*(n-1)/2') == SpecType.LEAN4
assert classify_spec_type('compare CM-0049 vs CM-0012') == SpecType.COMPARISON
assert classify_spec_type('CM-0049 mitigates T1422') == SpecType.RETRIEVAL

print('PASS')
" || { echo "FAIL"; exit 1; }

# Check 6: CLI help
echo -n "Check 6 - CLI help: "
if python3 "$SCRIPT_DIR/formalize.py" --help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "WARN: CLI help failed"
fi

# Check 7: YAML frontmatter
echo -n "Check 7 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "SKIP: Interactive interview loop (requires /interview skill and user input)"
echo "SKIP: ArangoDB entity verification (requires running ArangoDB)"
echo "SKIP: Lean4 goal verification (requires Lean4 toolchain)"
echo ""
echo "Result: PASS"
