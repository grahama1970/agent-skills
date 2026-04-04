#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== best-practices-plan sanity check ==="

# 1. SKILL.md exists and has frontmatter
echo "1. Checking SKILL.md..."
if grep -q "^name: best-practices-plan" "$SCRIPT_DIR/SKILL.md"; then
    echo "   PASS: SKILL.md has correct frontmatter"
else
    echo "   FAIL: SKILL.md missing or wrong name"
    exit 1
fi

# 2. run.sh help works
echo "2. Testing run.sh help..."
OUTPUT=$("$SCRIPT_DIR/run.sh" help 2>&1)
if echo "$OUTPUT" | grep -q "Conventions"; then
    echo "   PASS: help output contains expected text"
else
    echo "   FAIL: help output unexpected"
    exit 1
fi

# 3. run.sh rules outputs the SKILL.md
echo "3. Testing run.sh rules..."
OUTPUT=$("$SCRIPT_DIR/run.sh" rules 2>&1)
if echo "$OUTPUT" | grep -q "Adversarial Testing"; then
    echo "   PASS: rules output contains adversarial testing section"
else
    echo "   FAIL: rules output missing key section"
    exit 1
fi

# 4. Check delegates to /review-plan
echo "4. Testing delegation to /review-plan..."
REVIEW_PLAN="$SCRIPT_DIR/../review-plan/run.sh"
if [ -x "$REVIEW_PLAN" ]; then
    echo "   PASS: /review-plan exists and is executable"
else
    echo "   WARN: /review-plan not found (install it for full functionality)"
fi

echo "=== sanity check complete ==="
