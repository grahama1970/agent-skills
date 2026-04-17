#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== bootcamp sanity check ==="

OUTPUT="$(bash "${SCRIPT_DIR}/run.sh" start --role developer --dry-run 2>&1)"

PASS=0
FAIL=0

check_step() {
    local label="$1" pattern="$2"
    if echo "$OUTPUT" | grep -qi "$pattern"; then
        echo "  [PASS] Found step: $label"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] Missing step: $label (pattern: $pattern)"
        FAIL=$((FAIL + 1))
    fi
}

check_step "welcome"       "STEP 1.*Welcome"
check_step "health-check"  "STEP 2.*Health Check"
check_step "data-overview"  "STEP 3.*Data Overview"
check_step "first-query"   "STEP 4.*First Query"
check_step "baseline"      "STEP 5.*Compliance Baseline"

# Verify dry-run markers are present (should NOT have executed real skills)
if echo "$OUTPUT" | grep -q "\[dry-run\]"; then
    echo "  [PASS] Dry-run markers present"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] No dry-run markers found"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi

exit 0
