#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-assurance-case sanity check ==="

# export-dot --dry-run requires NO external deps (no ArangoDB, no graphviz)
OUTPUT=$("${SCRIPT_DIR}/run.sh" export-dot --control AC-1 --dry-run 2>&1)

PASS=true

# Validate DOT structure
for token in "digraph" "rankdir" "->"; do
    if ! echo "$OUTPUT" | grep -qF -- "$token"; then
        echo "FAIL: missing DOT token '$token'"
        PASS=false
    fi
done

# Validate GSN node types present (by shape or label content)
for gsn_marker in "Goal" "Strategy" "Solution" "Context"; do
    # Check for the marker in node labels (G1:, S1:, Sn1:, C1:) or shape attrs
    case "$gsn_marker" in
        Goal)     pattern="G1:" ;;
        Strategy) pattern="S1:" ;;
        Solution) pattern="Sn1:" ;;
        Context)  pattern="C1:" ;;
    esac
    if ! echo "$OUTPUT" | grep -q "$pattern"; then
        echo "FAIL: missing GSN $gsn_marker node (looked for '$pattern')"
        PASS=false
    fi
done

# Validate expected node shapes in DOT attrs
for shape in "box" "parallelogram" "circle"; do
    if ! echo "$OUTPUT" | grep -q "$shape"; then
        echo "FAIL: missing DOT shape '$shape'"
        PASS=false
    fi
done

if [ "$PASS" = true ]; then
    echo "PASS: all GSN node types and DOT structure verified"
    exit 0
else
    echo ""
    echo "--- DOT output ---"
    echo "$OUTPUT"
    exit 1
fi
