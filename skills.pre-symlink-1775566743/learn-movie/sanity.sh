#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== learn-movie Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh orchestrator.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: $f missing"
        exit 1
    fi
done
echo "OK"

# Check 2: run.sh is executable
echo -n "Check 2: run.sh executable... "
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable"
    exit 1
fi
echo "OK"

# Check 3: ffmpeg available (required for scene detection)
echo -n "Check 3: ffmpeg... "
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "FAIL: ffmpeg not found (required for scene detection)"
    exit 1
fi
echo "OK ($(ffmpeg -version 2>&1 | head -1))"

# Check 4: ffprobe available
echo -n "Check 4: ffprobe... "
if ! command -v ffprobe >/dev/null 2>&1; then
    echo "FAIL: ffprobe not found"
    exit 1
fi
echo "OK"

# Check 5: Python dependencies importable
echo -n "Check 5: Python dependencies... "
if ! python3 -c "import typer; import json; import shutil; import subprocess; from pathlib import Path" 2>/dev/null; then
    echo "FAIL: Missing Python deps (typer)"
    exit 1
fi
echo "OK"

# Check 6: uv available (used by run.sh)
echo -n "Check 6: uv available... "
if ! command -v uv >/dev/null 2>&1; then
    echo "FAIL: uv not found"
    exit 1
fi
echo "OK"

# Check 7: orchestrator.py loads without runtime errors
echo -n "Check 7: orchestrator module syntax... "
if ! python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/orchestrator.py').read())" 2>/dev/null; then
    echo "FAIL: orchestrator.py has syntax errors"
    exit 1
fi
echo "OK"

echo "Result: PASS"
