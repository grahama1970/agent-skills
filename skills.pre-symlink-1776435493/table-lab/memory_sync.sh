#!/bin/bash
# Sync queued patterns to /memory
#
# This script processes the memory_sync_queue.jsonl file and pushes
# each pattern to the memory service. Run this periodically or after
# batch tuning sessions.
#
# Usage: ./memory_sync.sh [--dry-run]

set -e

QUEUE_FILE="${HOME}/.pi/table-lab/memory_sync_queue.jsonl"
MEMORY_API="http://127.0.0.1:8601/learn"
PROCESSED_FILE="${HOME}/.pi/table-lab/memory_sync_processed.jsonl"

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "Dry run mode - no changes will be made"
fi

if [[ ! -f "$QUEUE_FILE" ]]; then
    echo "No queue file found at $QUEUE_FILE"
    exit 0
fi

COUNT=0
ERRORS=0

while IFS= read -r line; do
    if [[ -z "$line" ]]; then
        continue
    fi

    COUNT=$((COUNT + 1))

    if $DRY_RUN; then
        echo "Would sync: $(echo "$line" | jq -r '.problem[:50]')..."
        continue
    fi

    # Extract and send to memory
    RESULT=$(curl -s -X POST "$MEMORY_API" \
        -H "Content-Type: application/json" \
        -d "$line" \
        --connect-timeout 5 \
        --max-time 10 2>&1) || true

    if echo "$RESULT" | jq -e '.meta.ok' > /dev/null 2>&1; then
        echo "Synced: $(echo "$line" | jq -r '.problem[:50]')..."
        # Log to processed file
        echo "$line" >> "$PROCESSED_FILE"
    else
        echo "Failed: $(echo "$line" | jq -r '.problem[:50]')... - $RESULT"
        ERRORS=$((ERRORS + 1))
    fi

    # Small delay to avoid overwhelming the service
    sleep 0.2

done < "$QUEUE_FILE"

echo ""
echo "Processed: $COUNT patterns"
echo "Errors: $ERRORS"

if [[ $ERRORS -eq 0 && $DRY_RUN == false ]]; then
    # Clear the queue on success
    rm -f "$QUEUE_FILE"
    echo "Queue cleared"
fi
