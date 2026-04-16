#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== monitor-contacts sanity ==="

PASS=0
FAIL=0

# Check 1: SKILL.md exists
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] SKILL.md missing"
    FAIL=$((FAIL + 1))
fi

# Check 2: /discover-contacts skill available
if [[ -f "$SCRIPT_DIR/../discover-contacts/SKILL.md" ]]; then
    echo "  [PASS] /discover-contacts skill available"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] /discover-contacts skill not found"
    FAIL=$((FAIL + 1))
fi

# Check 3: /ops-discord skill available (for alerts)
if [[ -f "$SCRIPT_DIR/../ops-discord/SKILL.md" ]]; then
    echo "  [PASS] /ops-discord skill available"
    PASS=$((PASS + 1))
else
    echo "  [WARN] /ops-discord skill not found (alerts disabled)"
    PASS=$((PASS + 1))  # Non-fatal
fi

# Check 4: /scheduler skill available
if [[ -f "$SCRIPT_DIR/../scheduler/SKILL.md" ]]; then
    echo "  [PASS] /scheduler skill available"
    PASS=$((PASS + 1))
else
    echo "  [WARN] /scheduler skill not found (manual-only mode)"
    PASS=$((PASS + 1))  # Non-fatal
fi

# Check 5: References directory writable
REF_DIR="/mnt/storage12tb/media/personas/references"
if [[ -d "$REF_DIR" && -w "$REF_DIR" ]]; then
    echo "  [PASS] References directory writable: $REF_DIR"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] References directory not writable: $REF_DIR"
    FAIL=$((FAIL + 1))
fi

# Check 6: run.sh exists and is executable
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh executable"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] run.sh missing or not executable"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "Result: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && echo "Result: PASS" || echo "Result: FAIL"
exit $FAIL
