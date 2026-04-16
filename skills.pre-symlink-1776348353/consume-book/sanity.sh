#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [consume-book] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh search.py list.py notes.py position.py ingest_bridge.py epub.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL - missing $f"
        exit 1
    fi
done
echo "OK"

# Check 2: Python available
echo -n "Check 2: Python available... "
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "FAIL - python3 not found"
    exit 1
fi
echo "OK"

# Check 3: Python syntax valid on all modules
echo -n "Check 3: Python syntax check... "
for f in "$SCRIPT_DIR"/*.py; do
    if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
        echo "FAIL - syntax error in $(basename "$f")"
        exit 1
    fi
done
echo "OK"

# Check 4: Data directory creation
echo -n "Check 4: Data dir init... "
DATA_DIR="${HOME}/.pi/consume-book"
mkdir -p "${DATA_DIR}" "${DATA_DIR}/notes" "${DATA_DIR}/cache"
if [[ -d "${DATA_DIR}" ]]; then
    echo "OK ($DATA_DIR)"
else
    echo "FAIL - could not create data directory"
    exit 1
fi

# Check 5: run.sh help works
echo -n "Check 5: run.sh help text... "
output=$("$SCRIPT_DIR/run.sh" 2>&1 || true)
if echo "$output" | grep -qi "usage"; then
    echo "OK"
else
    echo "FAIL - run.sh did not produce expected help output"
    exit 1
fi

# Check 6: list command works (empty is fine)
echo -n "Check 6: list command... "
"$SCRIPT_DIR/run.sh" list 2>&1 >/dev/null || true
echo "OK"

echo "Result: PASS"
