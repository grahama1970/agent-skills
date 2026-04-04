#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [reality-check-sparta] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh check.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: run.sh is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh is not executable"
    exit 1
fi
echo "  run.sh is executable"

# Check 3: uv available
if ! command -v uv &>/dev/null; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "  uv available"

# Check 4: check.py is parseable
if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/check.py').read())" 2>/dev/null; then
    echo "  check.py parses without errors"
else
    echo "FAIL: check.py has syntax errors"
    exit 1
fi

# Check 5: Python stdlib imports
if python3 -c "
import argparse, json, os, random, re, shutil, subprocess, sys
from datetime import datetime
from pathlib import Path
" 2>/dev/null; then
    echo "  Python stdlib imports OK"
else
    echo "FAIL: Python stdlib imports failed"
    exit 1
fi

# Check 6: help command works
help_output=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$help_output" | grep -qi "SPARTA\|reality.*check\|adversarial"; then
    echo "  run.sh help works"
else
    echo "FAIL: run.sh help did not produce expected output"
    exit 1
fi

# Check 7: SPARTA project directory exists
SPARTA_DIR="/home/graham/workspace/experiments/sparta"
if [[ ! -d "$SPARTA_DIR" ]]; then
    echo "  SKIP: SPARTA project not found at $SPARTA_DIR"
    echo "Result: PASS (SPARTA project not available, live tests skipped)"
    exit 0
fi
echo "  SPARTA project found at $SPARTA_DIR"

# Check 8: Check for DuckDB availability (used by check.py)
cd "$SPARTA_DIR"
if uv run python3 -c "import duckdb" 2>/dev/null; then
    echo "  duckdb available in SPARTA venv"
else
    echo "  WARN: duckdb not importable in SPARTA project venv"
fi

# Check 9: Check for run data
RUNS_DIR="$SPARTA_DIR/data/runs"
if [[ -d "$RUNS_DIR" ]]; then
    run_count=$(ls "$RUNS_DIR" 2>/dev/null | wc -l)
    echo "  Found $run_count pipeline runs in $RUNS_DIR"
else
    echo "  WARN: No runs directory at $RUNS_DIR"
fi

echo "Result: PASS"
