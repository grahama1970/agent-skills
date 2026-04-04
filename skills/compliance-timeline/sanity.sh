#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== compliance-timeline sanity check ==="

# Run dry-run and capture output
OUTPUT=$("$SCRIPT_DIR/run.sh" show --days 30 --dry-run 2>/dev/null)
RC=$?

if [[ $RC -ne 0 ]]; then
    echo "FAIL: run.sh exited with code $RC"
    echo "$OUTPUT"
    exit 1
fi

# Verify header row exists
if ! echo "$OUTPUT" | head -1 | grep -q "TIMESTAMP.*ACTION.*SCOPE.*DOCUMENT.*DETAIL"; then
    echo "FAIL: missing expected column headers"
    echo "$OUTPUT"
    exit 1
fi

# Verify separator line
if ! echo "$OUTPUT" | sed -n '2p' | grep -q "^---"; then
    echo "FAIL: missing separator line"
    echo "$OUTPUT"
    exit 1
fi

# Count data rows (everything after header + separator)
DATA_ROWS=$(echo "$OUTPUT" | tail -n +3 | wc -l)
if [[ "$DATA_ROWS" -lt 5 ]]; then
    echo "FAIL: expected at least 5 data rows, got $DATA_ROWS"
    echo "$OUTPUT"
    exit 1
fi

# Verify chronological order (timestamps should be sorted ascending)
TIMESTAMPS=$(echo "$OUTPUT" | tail -n +3 | awk -F'|' '{print $1}' | sed 's/ *$//')
SORTED=$(echo "$TIMESTAMPS" | sort)
if [[ "$TIMESTAMPS" != "$SORTED" ]]; then
    echo "FAIL: timestamps are not in chronological order"
    echo "$OUTPUT"
    exit 1
fi

# Verify known actions appear
for ACTION in CREATE UPDATE LINK FLAG DELETE; do
    if ! echo "$OUTPUT" | grep -q "$ACTION"; then
        echo "FAIL: missing expected action $ACTION"
        echo "$OUTPUT"
        exit 1
    fi
done

# Test scope filtering
SCOPE_OUTPUT=$("$SCRIPT_DIR/run.sh" show --scope sparta --dry-run 2>/dev/null)
if echo "$SCOPE_OUTPUT" | tail -n +3 | grep -v "^$" | awk -F'|' '{print $3}' | grep -qv " *sparta *"; then
    echo "FAIL: scope filter leaked non-sparta rows"
    echo "$SCOPE_OUTPUT"
    exit 1
fi

# Test diff subcommand dry-run
DIFF_OUTPUT=$("$SCRIPT_DIR/run.sh" diff --from 2026-01-01 --to 2026-02-01 --dry-run 2>/dev/null)
if [[ $? -ne 0 ]]; then
    echo "FAIL: diff --dry-run exited non-zero"
    echo "$DIFF_OUTPUT"
    exit 1
fi

echo "PASS: all sanity checks passed ($DATA_ROWS timeline entries, chronological, columns valid)"
exit 0
