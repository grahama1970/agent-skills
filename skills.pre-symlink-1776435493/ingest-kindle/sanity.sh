#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $label"
        ((PASS++))
    else
        echo "  ✗ $label"
        ((FAIL++))
    fi
}

echo "=== ingest-kindle sanity ==="

# Check uv is available
check "uv available" command -v uv

# Check run.sh exists and is executable
check "run.sh exists" test -x "$SCRIPT_DIR/run.sh"

# Check Python files exist
check "kindle_ingest.py exists" test -f "$SCRIPT_DIR/kindle_ingest.py"
check "clippings.py exists" test -f "$SCRIPT_DIR/clippings.py"
check "formats.py exists" test -f "$SCRIPT_DIR/formats.py"
check "memory_integration.py exists" test -f "$SCRIPT_DIR/memory_integration.py"

# Check pyproject.toml
check "pyproject.toml exists" test -f "$SCRIPT_DIR/pyproject.toml"

# Check help works
check "run.sh --help" "$SCRIPT_DIR/run.sh" --help

# Check health command
check "run.sh health" "$SCRIPT_DIR/run.sh" health

# Optional: check calibre
if command -v ebook-convert >/dev/null 2>&1; then
    echo "  ✓ calibre ebook-convert available (optional)"
    ((PASS++))
else
    echo "  ⚠ calibre ebook-convert not found (optional — needed for .mobi/.azw3)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
