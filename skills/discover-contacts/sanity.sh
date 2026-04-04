#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== discover-contacts sanity ==="

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

# Check 2: References directory exists
REF_DIR="/mnt/storage12tb/media/personas/references"
if [[ -d "$REF_DIR" ]]; then
    echo "  [PASS] References directory exists: $REF_DIR"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] References directory missing: $REF_DIR"
    FAIL=$((FAIL + 1))
fi

# Check 3: ARCOS contacts CSV exists
CSV="$REF_DIR/darpa_arcos_contacts.csv"
if [[ -f "$CSV" ]]; then
    LINE_COUNT=$(wc -l < "$CSV")
    echo "  [PASS] ARCOS contacts CSV exists ($LINE_COUNT lines)"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] ARCOS contacts CSV missing: $CSV"
    FAIL=$((FAIL + 1))
fi

# Check 4: /dogpile skill available
if [[ -f "$SCRIPT_DIR/../dogpile/SKILL.md" ]]; then
    echo "  [PASS] /dogpile skill available"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] /dogpile skill not found"
    FAIL=$((FAIL + 1))
fi

# Check 5: /memory skill available
if [[ -f "$SCRIPT_DIR/../memory/SKILL.md" ]]; then
    echo "  [PASS] /memory skill available"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] /memory skill not found"
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
