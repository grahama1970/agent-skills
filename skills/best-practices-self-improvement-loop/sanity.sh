#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== best-practices-self-improvement-loop sanity check ==="

# Check SKILL.md exists and has content
if [ ! -f "$SCRIPT_DIR/SKILL.md" ]; then
    echo "FAIL: SKILL.md missing"
    exit 1
fi

# Check the 6 rules are documented
for rule in "MUST be in code" "try → measure → compare to gate" "ordered and exhausted deterministically" "full audit trail" "Pre-flight" "written to disk after every iteration"; do
    if ! grep -q "$rule" "$SCRIPT_DIR/SKILL.md"; then
        echo "FAIL: Missing rule: $rule"
        exit 1
    fi
done

# Check reference implementations are documented
for ref in "data_enrichment.py" "training_loop.py" "pipeline.py"; do
    if ! grep -q "$ref" "$SCRIPT_DIR/SKILL.md"; then
        echo "FAIL: Missing reference: $ref"
        exit 1
    fi
done

# Check the referenced scripts actually exist
CLF_SCRIPTS="$(dirname "$SCRIPT_DIR")/classifier-lab/scripts"
for script in "data_enrichment.py" "training_loop.py" "pipeline.py"; do
    if [ ! -f "$CLF_SCRIPTS/$script" ]; then
        echo "WARN: Reference implementation not found: $CLF_SCRIPTS/$script"
    else
        echo "OK: $script exists"
    fi
done

echo "PASS: all checks passed"
