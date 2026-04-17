#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== sync-sites sanity check ==="

output=$("$SCRIPT_DIR/run.sh" status --dry-run)

errors=0

if ! echo "$output" | grep -q '"hash"'; then
    echo "FAIL: output missing deployment hash field"
    errors=$((errors + 1))
fi

if ! echo "$output" | grep -q '"origin"'; then
    echo "FAIL: output missing origin field"
    errors=$((errors + 1))
fi

if ! echo "$output" | grep -q '"refspec"'; then
    echo "FAIL: output missing refspec field"
    errors=$((errors + 1))
fi

if [[ $errors -gt 0 ]]; then
    echo "FAIL: $errors field(s) missing from dry-run status output"
    exit 1
fi

echo "PASS: status --dry-run contains hash, origin, and refspec fields"
exit 0
