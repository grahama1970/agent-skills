#!/usr/bin/env bash
# Sanity check for best-practices-kde
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== best-practices-kde sanity check ==="

# 1. Check SKILL.md exists and has required sections
echo "1/3 Checking SKILL.md exists and is readable..."
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi

# 2. Validate SKILL.md has key sections
echo "2/3 Validating SKILL.md content..."
if ! grep -q "design-singleton-style" "$SCRIPT_DIR/SKILL.md"; then
    echo "FAIL: SKILL.md missing design-singleton-style rule"
    exit 1
fi

if ! grep -q "a11y-interactive-elements" "$SCRIPT_DIR/SKILL.md"; then
    echo "FAIL: SKILL.md missing a11y-interactive-elements rule"
    exit 1
fi

if ! grep -q "perf-binding-loops" "$SCRIPT_DIR/SKILL.md"; then
    echo "FAIL: SKILL.md missing perf-binding-loops rule"
    exit 1
fi

# 3. Check that it has rules in all major categories
echo "3/3 Checking rule categories..."
for category in "design-" "a11y-" "perf-" "integration-" "style-" "correctness-"; do
    if ! grep -q "$category" "$SCRIPT_DIR/SKILL.md"; then
        echo "WARNING: No rules in category $category"
    fi
done

echo "best-practices-kde sanity check PASSED"
