#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [create-intent-map] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: uv available
echo -n "Check 2: uv available... "
if ! command -v uv &>/dev/null; then
    echo "FAIL - uv not found"
    exit 1
fi
echo "OK"

# Check 3: Docker available (needed for SFT training)
echo -n "Check 3: Docker available... "
if command -v docker &>/dev/null; then
    echo "OK"
else
    echo "SKIP - docker not found (needed for SFT training only)"
fi

# Check 4: HF_TOKEN check
echo -n "Check 4: HF_TOKEN... "
if [[ -n "${HF_TOKEN:-}" ]]; then
    echo "OK (set)"
else
    echo "SKIP - HF_TOKEN not set (required for training)"
fi

# Check 5: Core Python imports (lightweight check)
echo -n "Check 5: Core Python imports... "
if ! python3 -c "
import json
import os
from pathlib import Path
" 2>/dev/null; then
    echo "FAIL - basic Python imports failed"
    exit 1
fi
echo "OK"

# Check 6: Check if scripts directory has Python files with valid syntax
echo -n "Check 6: Script syntax check... "
scripts_dir="$SCRIPT_DIR/scripts"
if [[ -d "$scripts_dir" ]]; then
    fail_count=0
    for f in "$scripts_dir"/*.py; do
        [[ ! -f "$f" ]] && continue
        if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
            echo ""
            echo "  WARN: syntax issue in $(basename "$f")"
            ((fail_count++)) || true
        fi
    done
    if [[ $fail_count -eq 0 ]]; then
        echo "OK"
    else
        echo "WARN - $fail_count files with syntax issues"
    fi
else
    echo "SKIP - scripts/ directory not found"
fi

# Check 7: run.sh help works
echo -n "Check 7: run.sh help... "
output=$("$SCRIPT_DIR/run.sh" help 2>&1 || true)
if echo "$output" | grep -qi "intent\|training\|grpo"; then
    echo "OK"
else
    echo "FAIL - run.sh did not produce expected help"
    exit 1
fi

echo "Result: PASS"
