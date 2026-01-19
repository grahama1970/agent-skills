#!/usr/bin/env bash
#
# Sanity check for embedding skill
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Embedding Skill Sanity Check ==="

# Check info command works
echo "1. Testing info command..."
"$SCRIPT_DIR/run.sh" info

# Check embed command works
echo ""
echo "2. Testing embed command..."
result=$("$SCRIPT_DIR/run.sh" embed --text "test query" --local)
echo "$result" | head -c 200

# Validate JSON output
if echo "$result" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'vector' in d; assert len(d['vector']) > 0; print(f'✓ Got {len(d[\"vector\"])}-dim vector')"; then
    echo "=== SANITY CHECK PASSED ==="
    exit 0
else
    echo "=== SANITY CHECK FAILED ==="
    exit 1
fi
