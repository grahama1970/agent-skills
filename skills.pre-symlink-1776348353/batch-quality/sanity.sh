#!/bin/bash
#
# Sanity check for batch-quality skill
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Batch Quality Sanity Check ==="

# Check 1: CLI loads
echo -n "1. CLI loads... "
if uv run python cli.py --help >/dev/null 2>&1; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# Check 2: Preflight command works (dry run)
echo -n "2. Preflight dry-run... "
if uv run python cli.py preflight --stage test --dry-run 2>&1 | grep -q "PREFLIGHT"; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# Check 3: Status command works
echo -n "3. Status command... "
if uv run python cli.py status 2>&1 | grep -q "status"; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# Check 4: Clear command works
echo -n "4. Clear command... "
if uv run python cli.py clear 2>&1 | grep -qE "(cleared|No preflight)"; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

echo ""
echo "All sanity checks passed!"
