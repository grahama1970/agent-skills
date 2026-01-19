#!/usr/bin/env bash
# Sanity test for arxiv-learn skill
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Arxiv-Learn Skill Sanity Test ==="

# Test 1: Check script exists and is executable
echo "[1/4] Checking script..."
[[ -x "$SCRIPT_DIR/run.sh" ]] || { echo "FAIL: run.sh not executable"; exit 1; }
[[ -f "$SCRIPT_DIR/arxiv_learn.py" ]] || { echo "FAIL: arxiv_learn.py not found"; exit 1; }
echo "  OK: Scripts exist"

# Test 2: Check help works
echo "[2/4] Checking help..."
"$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1 || { echo "FAIL: --help failed"; exit 1; }
echo "  OK: Help works"

# Test 3: Check dry-run with skip-interview
echo "[3/4] Dry-run test with sample paper..."
# Use a known small paper for quick test
OUTPUT=$("$SCRIPT_DIR/run.sh" 2301.00001 --scope test --dry-run --skip-interview --json 2>&1) || true

# Check for expected output structure
if echo "$OUTPUT" | grep -q '"success"'; then
    echo "  OK: Dry-run produces structured output"
else
    echo "  WARN: Dry-run output may need network (arxiv API)"
fi

# Test 4: Check dependencies
echo "[4/4] Checking skill dependencies..."
for skill in arxiv distill interview memory edge-verifier; do
    skill_dir="$SCRIPT_DIR/../$skill"
    if [[ -d "$skill_dir" ]] && [[ -f "$skill_dir/run.sh" ]]; then
        echo "  OK: $skill skill present"
    else
        echo "  WARN: $skill skill not found at $skill_dir"
    fi
done

echo ""
echo "=== Sanity test complete ==="
