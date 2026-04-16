#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== consume-movie Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh search.py clips.py notes.py list.py ingest_bridge.py watch.py pyproject.toml; do
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

# Check 3: Python dependencies importable (via uv, matching how run.sh invokes)
echo -n "Check 3: Python dependencies... "
PYTHONPATH="${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
if ! uv run --directory "$SCRIPT_DIR" python -c "import srt; import rich; import json; from pathlib import Path" 2>/dev/null; then
    echo "FAIL: Missing Python deps (srt, rich)"
    echo "  Run: cd $SCRIPT_DIR && uv sync"
    exit 1
fi
echo "OK"

# Check 4: consume_common package available
echo -n "Check 4: consume_common package... "
if ! uv run --directory "$SCRIPT_DIR" python -c "from consume_common.registry import ContentRegistry" 2>/dev/null; then
    echo "FAIL: consume_common.registry not importable"
    echo "  Ensure consume_common/ exists at $SCRIPT_DIR/../consume_common/"
    exit 1
fi
echo "OK"

# Check 5: ffmpeg available (needed for clip extraction)
echo -n "Check 5: ffmpeg... "
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "WARN (ffmpeg not found; clip extraction will fail)"
else
    echo "OK"
fi

# Check 6: Data directory writable
echo -n "Check 6: Data directory... "
DATA_DIR="${HOME}/.pi/consume-movie"
mkdir -p "$DATA_DIR" 2>/dev/null
if [[ ! -w "$DATA_DIR" ]]; then
    echo "FAIL: $DATA_DIR not writable"
    exit 1
fi
echo "OK ($DATA_DIR)"

# Check 7: run.sh info command works
echo -n "Check 7: info command... "
if ! "$SCRIPT_DIR/run.sh" info >/dev/null 2>&1; then
    echo "FAIL: run.sh info failed"
    exit 1
fi
echo "OK"

echo "Result: PASS"
