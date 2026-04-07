#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== monitor-drift-sensors sanity check ==="

output=$("${SCRIPT_DIR}/run.sh" analyze --dry-run 2>&1)
echo "$output"

# Check that at least one drift point was detected
drift_count=$(echo "$output" | grep -cE '^\s*[0-9]+\s+\|' || true)
if [[ $drift_count -lt 1 ]]; then
    echo "FAIL: no drift points detected" >&2
    exit 1
fi
echo "OK: $drift_count drift point(s) detected"

# Check that the first drift point is between samples 13-20
first_idx=$(echo "$output" | grep -E '^\s*[0-9]+\s+\|' | head -1 | awk '{print $1}')
if [[ $first_idx -ge 13 ]] && [[ $first_idx -le 20 ]]; then
    echo "OK: first drift at sample $first_idx (expected 13-20)"
else
    echo "FAIL: first drift at sample $first_idx (expected 13-20)" >&2
    exit 1
fi

echo "=== sanity PASSED ==="
