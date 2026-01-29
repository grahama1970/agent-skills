#!/usr/bin/env bash
# Sanity check for compliance-ops skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== compliance-ops sanity check ==="

# Check 1: run.sh --help works
echo "[1/4] Testing run.sh --help..."
if ./run.sh --help > /dev/null 2>&1; then
    echo "  ✓ run.sh --help works"
else
    echo "  ✗ run.sh --help failed"
    exit 1
fi

# Check 2: Python imports succeed
echo "[2/4] Testing Python imports..."
if python -c "import compliance_ops; print('  ✓ compliance_ops imports')"; then
    :
else
    echo "  ✗ compliance_ops import failed"
    exit 1
fi

# Check 3: CLI version command works
echo "[3/4] Testing version command..."
VERSION=$(python compliance_ops.py version 2>&1)
if [[ "$VERSION" == *"compliance-ops"* ]]; then
    echo "  ✓ version command works: $VERSION"
else
    echo "  ✗ version command failed"
    exit 1
fi

# Check 4: frameworks list command works
echo "[4/4] Testing frameworks command..."
if python compliance_ops.py frameworks 2>&1 | grep -q "soc2"; then
    echo "  ✓ frameworks command lists soc2"
else
    echo "  ✗ frameworks command failed"
    exit 1
fi

echo ""
echo "=== sanity check PASSED ==="
exit 0
