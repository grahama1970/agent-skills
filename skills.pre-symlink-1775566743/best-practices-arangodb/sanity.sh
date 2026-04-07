#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRORS=0

echo "=== best-practices-arangodb sanity ==="

# 1. Required files
for f in SKILL.md run.sh; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        ERRORS=$((ERRORS + 1))
    fi
done

# 2. SKILL.md has triggers
if ! grep -q "triggers:" "$SCRIPT_DIR/SKILL.md"; then
    echo "FAIL: SKILL.md missing triggers"
    ERRORS=$((ERRORS + 1))
fi

# 3. run.sh is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable"
    ERRORS=$((ERRORS + 1))
fi

# 4. Composed skill exists
INGEST_CODE="$(cd "$SCRIPT_DIR/.." && pwd)/ingest-code/run.sh"
if [[ ! -f "$INGEST_CODE" ]]; then
    echo "FAIL: /ingest-code not found at $INGEST_CODE"
    ERRORS=$((ERRORS + 1))
fi

# 5. References dir exists with content
if [[ ! -d "$SCRIPT_DIR/references" ]]; then
    echo "FAIL: references/ directory missing"
    ERRORS=$((ERRORS + 1))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo "FAILED ($ERRORS errors)"
    exit 1
fi

echo "PASSED"
