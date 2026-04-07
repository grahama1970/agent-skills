#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== consume-music Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh search.py list.py notes.py ingest_bridge.py __init__.py; do
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

# Check 3: Python dependencies importable
echo -n "Check 3: Python dependencies... "
PYTHONPATH="${SCRIPT_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
if ! python3 -c "import rich; import json; from pathlib import Path" 2>/dev/null; then
    echo "FAIL: Missing Python deps (rich)"
    exit 1
fi
echo "OK"

# Check 4: consume_common package available
echo -n "Check 4: consume_common package... "
if ! python3 -c "from consume_common.registry import ContentRegistry" 2>/dev/null; then
    echo "FAIL: consume_common.registry not importable"
    echo "  Ensure consume_common/ exists at $SCRIPT_DIR/../consume_common/"
    exit 1
fi
echo "OK"

# Check 5: search module loads
echo -n "Check 5: search module... "
if ! python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); from search import BRIDGE_KEYWORDS; assert len(BRIDGE_KEYWORDS) > 0" 2>/dev/null; then
    echo "FAIL: search module broken or BRIDGE_KEYWORDS empty"
    exit 1
fi
echo "OK"

# Check 6: Data directory writable
echo -n "Check 6: Data directory... "
DATA_DIR="${HOME}/.pi/consume-music"
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
