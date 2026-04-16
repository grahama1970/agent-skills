#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "[PASS] $label"
        PASS=$((PASS + 1))
    else
        echo "[FAIL] $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== dum-dum sanity check ==="

# File presence
check "SKILL.md exists"    test -f "$SCRIPT_DIR/SKILL.md"
check "run.sh exists"      test -f "$SCRIPT_DIR/run.sh"
check "run.sh executable"  test -x "$SCRIPT_DIR/run.sh"
check "pyproject.toml"     test -f "$SCRIPT_DIR/pyproject.toml"
check "probe.py exists"    test -f "$SCRIPT_DIR/probe.py"
check "collect.py exists"  test -f "$SCRIPT_DIR/collect.py"
check "drift.py exists"    test -f "$SCRIPT_DIR/drift.py"
check "status.py exists"   test -f "$SCRIPT_DIR/status.py"
check "dashboard.py exists" test -f "$SCRIPT_DIR/dashboard.py"

# Probe dry-run
echo ""
echo "--- probe --dry-run ---"
probe_out=$("$SCRIPT_DIR/run.sh" probe --dry-run 2>&1)
echo "$probe_out"

if echo "$probe_out" | grep -q "Grade:.*A"; then
    echo "[PASS] probe dry-run grade A"
    PASS=$((PASS + 1))
else
    echo "[FAIL] probe dry-run did not produce grade A"
    FAIL=$((FAIL + 1))
fi

if echo "$probe_out" | grep -q "4/4 passed"; then
    echo "[PASS] all 4 probes passed"
    PASS=$((PASS + 1))
else
    echo "[FAIL] expected 4/4 probes passed"
    FAIL=$((FAIL + 1))
fi

# Collect dry-run
echo ""
echo "--- collect --dry-run ---"
collect_out=$("$SCRIPT_DIR/run.sh" collect --dry-run 2>&1)
echo "$collect_out"

if echo "$collect_out" | grep -q "Signals: 5"; then
    echo "[PASS] collect dry-run found 5 signals"
    PASS=$((PASS + 1))
else
    echo "[FAIL] expected 5 fixture signals"
    FAIL=$((FAIL + 1))
fi

# Drift dry-run
echo ""
echo "--- drift --dry-run ---"
drift_out=$("$SCRIPT_DIR/run.sh" drift --dry-run 2>&1)
echo "$drift_out"

if echo "$drift_out" | grep -q "Drift alerts:"; then
    echo "[PASS] drift dry-run ran"
    PASS=$((PASS + 1))
else
    echo "[FAIL] drift dry-run failed"
    FAIL=$((FAIL + 1))
fi

# Status
echo ""
echo "--- status ---"
status_out=$("$SCRIPT_DIR/run.sh" status 2>&1)
echo "$status_out"

if echo "$status_out" | grep -q "Last probe:"; then
    echo "[PASS] status shows probe info"
    PASS=$((PASS + 1))
else
    echo "[FAIL] status missing probe info"
    FAIL=$((FAIL + 1))
fi

# Dashboard export
echo ""
echo "--- dashboard ---"
dash_out=$("$SCRIPT_DIR/run.sh" dashboard 2>&1)
echo "$dash_out"

if echo "$dash_out" | grep -q "Dashboard exported"; then
    echo "[PASS] dashboard exported"
    PASS=$((PASS + 1))
else
    echo "[FAIL] dashboard export failed"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
echo "=== sanity PASSED ==="
