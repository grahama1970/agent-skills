#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_DIR="$SCRIPT_DIR"

echo "=== Scillm Skill Sanity (Hardened) ==="

# 1. Structure Check
if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    echo "  [FAIL] pyproject.toml missing"
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [FAIL] run.sh missing"
    exit 1
fi

# 2. Execution Check (Trigger uv sync)
echo "  [INFO] Verifying batch CLI (triggers uv sync)..."
OUTPUT=$("$SCRIPT_DIR/run.sh" batch --help 2>&1)
if echo "$OUTPUT" | grep -q "Usage:"; then
    echo "  [PASS] batch CLI works"
else
    echo "  [FAIL] batch CLI failed"
    echo "$OUTPUT"
    exit 1
fi

echo "  [INFO] Verifying vlm CLI..."
OUTPUT_VLM=$("$SCRIPT_DIR/run.sh" vlm --help 2>&1)
if echo "$OUTPUT_VLM" | grep -q "Usage:"; then
    echo "  [PASS] vlm CLI works"
else
    echo "  [FAIL] vlm CLI failed"
    echo "$OUTPUT_VLM"
    exit 1
fi

echo "Result: PASS"
