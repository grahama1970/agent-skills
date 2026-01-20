#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Arxiv Learn Sanity ==="
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi
if "$SCRIPT_DIR/run.sh" --help >/dev/null; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi
echo "Result: PASS"
