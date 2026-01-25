#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Codex Skill Sanity ==="

# Check run.sh
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists"
else
    echo "  [FAIL] run.sh missing"
    exit 1
fi

# Check --help
if "$SCRIPT_DIR/run.sh" --help >/dev/null; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# Check codex CLI
if command -v codex &> /dev/null; then
    echo "  [PASS] 'codex' CLI found"
else
    echo "  [FAIL] 'codex' CLI missing"
    exit 1
fi

# Functional Check: Reasoning
echo "  [INFO] Running functional reasoning test..."
if "$SCRIPT_DIR/run.sh" reason "What is 2+2?" | grep -q "4"; then
    echo "  [PASS] Functional reasoning test (2+2=4)"
else
    echo "  [FAIL] Functional reasoning test failed"
    exit 1
fi

# Functional Check: Extraction
echo "  [INFO] Running functional extraction test..."
EXTRACTION=$("$SCRIPT_DIR/run.sh" extract "This is a test. The sky is blue." --schema "$SCRIPT_DIR/dogpile_schema.json")
if echo "$EXTRACTION" | grep -q "\"is_ambiguous\":"; then
    echo "  [PASS] Functional extraction test (JSON schema)"
else
    echo "  [FAIL] Functional extraction test failed"
    echo "         Output: $EXTRACTION"
    exit 1
fi

echo "Result: PASS"

