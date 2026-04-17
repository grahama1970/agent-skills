#!/bin/bash
# ops-runpod sanity test - verifies all CLI commands work with value validation
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Ops-RunPod Sanity Tests ==="
PASS=0
FAIL=0

# Test 1: run.sh exists and is executable
echo -n "  [1] run.sh exists and executable... "
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "[PASS]"
    PASS=$((PASS+1))
else
    echo "[FAIL]"
    FAIL=$((FAIL+1))
fi

# Test 2: Help command works
echo -n "  [2] Help command... "
if ./run.sh --help > /tmp/runpod_sanity_out.txt 2>&1; then
    echo "[PASS]"
    PASS=$((PASS+1))
else
    echo "[FAIL]"
    FAIL=$((FAIL+1))
fi

# Test 3: estimate-cost with decimal model size (bug fix verification)
echo -n "  [3] estimate-cost 1.5B (decimal parsing)... "
if ./run.sh estimate-cost 1.5B --hours 1 > /tmp/runpod_sanity_out.txt 2>&1; then
    if grep -q "Cost Estimate" /tmp/runpod_sanity_out.txt; then
        # VALUE VALIDATION: Check cost is reasonable (not $290000)
        if grep -q "290000" /tmp/runpod_sanity_out.txt; then
            echo "[FAIL - unreasonable cost $290k]"
            FAIL=$((FAIL+1))
        else
            echo "[PASS]"
            PASS=$((PASS+1))
        fi
    else
        echo "[FAIL - no output]"
        FAIL=$((FAIL+1))
    fi
else
    echo "[FAIL]"
    cat /tmp/runpod_sanity_out.txt | head -3
    FAIL=$((FAIL+1))
fi

# Test 4: estimate-cost with standard model size
echo -n "  [4] estimate-cost 7B... "
if ./run.sh estimate-cost 7B --hours 2 > /tmp/runpod_sanity_out.txt 2>&1; then
    echo "[PASS]"
    PASS=$((PASS+1))
else
    echo "[FAIL]"
    FAIL=$((FAIL+1))
fi

# Test 5: optimize command with 7B
echo -n "  [5] optimize 7B... "
if ./run.sh optimize 7B --tokens 100000 > /tmp/runpod_sanity_out.txt 2>&1; then
    if grep -q "Optimal Configuration" /tmp/runpod_sanity_out.txt; then
        echo "[PASS]"
        PASS=$((PASS+1))
    else
        echo "[FAIL - no config output]"
        FAIL=$((FAIL+1))
    fi
else
    echo "[FAIL]"
    FAIL=$((FAIL+1))
fi

# Test 6: optimize command with 1.5B (decimal model size in optimizer)
echo -n "  [6] optimize 1.5B (decimal in optimizer)... "
if ./run.sh optimize 1.5B --tokens 100000 > /tmp/runpod_sanity_out.txt 2>&1; then
    if grep -q "Optimal Configuration" /tmp/runpod_sanity_out.txt; then
        # VALUE VALIDATION: Check tokens/hour is not 0
        if grep -q "Tokens per Hour.*│ 0" /tmp/runpod_sanity_out.txt; then
            echo "[FAIL - zero throughput]"
            FAIL=$((FAIL+1))
        else
            echo "[PASS]"
            PASS=$((PASS+1))
        fi
    else
        echo "[FAIL - no config output]"
        FAIL=$((FAIL+1))
    fi
else
    echo "[FAIL]"
    FAIL=$((FAIL+1))
fi

# Test 7: list-instances (may be empty, but should not error)
echo -n "  [7] list-instances... "
if ./run.sh list-instances > /tmp/runpod_sanity_out.txt 2>&1; then
    if grep -q "RunPod Instances" /tmp/runpod_sanity_out.txt; then
        echo "[PASS]"
        PASS=$((PASS+1))
    else
        echo "[FAIL - no table output]"
        FAIL=$((FAIL+1))
    fi
else
    echo "[FAIL]"
    FAIL=$((FAIL+1))
fi

# Test 8: deploy-docker help (verifies import os fix)
echo -n "  [8] deploy-docker --help (import os)... "
if ./run.sh deploy-docker --help > /tmp/runpod_sanity_out.txt 2>&1; then
    if grep -q "Deploy a Docker image" /tmp/runpod_sanity_out.txt; then
        echo "[PASS]"
        PASS=$((PASS+1))
    else
        echo "[FAIL - no help output]"
        FAIL=$((FAIL+1))
    fi
else
    echo "[FAIL - likely NameError]"
    cat /tmp/runpod_sanity_out.txt | head -3
    FAIL=$((FAIL+1))
fi

# Summary
echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

if [[ $FAIL -eq 0 ]]; then
    echo "Result: PASS"
    exit 0
else
    echo "Result: FAIL"
    exit 1
fi
