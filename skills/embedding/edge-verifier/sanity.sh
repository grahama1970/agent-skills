#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Edge Verifier Skill Sanity Tests ==="

echo "1. Script availability"
if [[ -f "$SCRIPT_DIR/verify_edges.py" ]]; then
    echo "  [PASS] verify_edges.py exists"
else
    echo "  [FAIL] verify_edges.py missing"
    exit 1
fi

echo "2. Help command (verifies imports)"
if "$SCRIPT_DIR/run.sh" --help > /dev/null 2>&1; then
     echo "  [PASS] run.sh --help works"
else
     echo "  [FAIL] run.sh --help failed"
     exit 1
fi

echo ""
echo "Result: PASS"
exit 0
