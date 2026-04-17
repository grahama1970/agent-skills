#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== benchmark-models sanity check ==="

# Run dry-run benchmark
OUTPUT=$("$SCRIPT_DIR/run.sh" run --model mock --suite compliance-basic --dry-run 2>&1)

# Validate output contains expected structure
PASS=0
FAIL=0

check() {
    local label="$1"
    local pattern="$2"
    if echo "$OUTPUT" | grep -q "$pattern"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label (pattern '$pattern' not found)"
        FAIL=$((FAIL + 1))
    fi
}

check "has test cases"        "NIST-AC-1"
check "has accuracy metric"   "accuracy:"
check "has latency_p50"       "latency_p50:"
check "has latency_p95"       "latency_p95:"
check "has cost estimate"     "est_cost:"
check "has PASS results"      "PASS"
check "has domain column"     "NIST 800-171"
check "has drift domain"      "Cross-Program Drift"
check "has 20 test rows"      "DRIFT-CNC"
check "results saved"         "benchmark_results.json"

echo ""
echo "sanity: $PASS passed, $FAIL failed"

if [[ $FAIL -gt 0 ]]; then
    echo "SANITY FAILED"
    exit 1
fi

echo "SANITY PASSED"
exit 0
