#!/usr/bin/env bash
# Sanity tests for treesitter-tools skill
# Run: ./sanity.sh
# Exit codes: 0 = all pass, 1 = failures

set -euo pipefail

# Load environment from common .env files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common.sh" 2>/dev/null || true

PASS=0
FAIL=0
MISSING_DEPS=()

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }
log_missing() {
    echo "  [MISS] $1"
    MISSING_DEPS+=("$2")
}

echo "=== Treesitter Tools Skill Sanity Tests ==="
echo ""

# -----------------------------------------------------------------------------
# 1. CLI availability
# -----------------------------------------------------------------------------
echo "1. CLI availability"

if command -v treesitter-tools &>/dev/null; then
    log_pass "treesitter-tools CLI found: $(command -v treesitter-tools)"
else
    log_missing "treesitter-tools CLI not found" "pip install -e /path/to/treesitter-tools"
    echo ""
    echo "Result: INCOMPLETE (CLI not installed)"
    exit 0
fi

# -----------------------------------------------------------------------------
# 2. Help commands
# -----------------------------------------------------------------------------
echo "2. Help commands"

if treesitter-tools --help &>/dev/null; then
    log_pass "treesitter-tools --help"
else
    log_fail "treesitter-tools --help"
fi

for cmd in symbols scan query; do
    if treesitter-tools "$cmd" --help &>/dev/null; then
        log_pass "$cmd --help"
    else
        log_fail "$cmd --help"
    fi
done

# -----------------------------------------------------------------------------
# 3. Python imports
# -----------------------------------------------------------------------------
echo "3. Python imports"

if python3 -c "from treesitter_tools import api" 2>/dev/null; then
    log_pass "treesitter_tools.api import"
else
    log_fail "treesitter_tools.api import"
fi

if python3 -c "from treesitter_tools.core import scan_directory, outline_markdown" 2>/dev/null; then
    log_pass "treesitter_tools.core imports"
else
    log_fail "treesitter_tools.core imports"
fi

# -----------------------------------------------------------------------------
# 4. Functional test - symbols
# -----------------------------------------------------------------------------
echo "4. Functional test - symbols"

# Create a temp Python file to test
TEMP_FILE=$(mktemp --suffix=.py)
cat > "$TEMP_FILE" << 'EOF'
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

class Greeter:
    """A class that greets."""
    def greet(self, name: str) -> str:
        return hello(name)
EOF

SYMBOLS_OUTPUT=$(treesitter-tools symbols "$TEMP_FILE" 2>&1 || echo "error")
rm -f "$TEMP_FILE"

if echo "$SYMBOLS_OUTPUT" | grep -q "hello"; then
    log_pass "symbols extracts function 'hello'"
else
    log_fail "symbols failed to extract function"
fi

if echo "$SYMBOLS_OUTPUT" | grep -q "Greeter"; then
    log_pass "symbols extracts class 'Greeter'"
else
    log_fail "symbols failed to extract class"
fi

# -----------------------------------------------------------------------------
# 5. Functional test - scan
# -----------------------------------------------------------------------------
echo "5. Functional test - scan"

# Scan the treesitter-tools source itself
SCAN_OUTPUT=$(treesitter-tools scan /home/graham/workspace/experiments/treesitter-tools/src --include "**/*.py" 2>&1 | head -50 || echo "error")

if echo "$SCAN_OUTPUT" | grep -q "treesitter_tools"; then
    log_pass "scan finds treesitter_tools source"
else
    log_fail "scan failed"
fi

# -----------------------------------------------------------------------------
# 6. Language detection
# -----------------------------------------------------------------------------
echo "6. Language detection"

LANG_TEST=$(python3 -c "
from treesitter_tools.core import detect_language
from pathlib import Path

assert detect_language(Path('test.py')) == 'python'
assert detect_language(Path('test.js')) == 'javascript'
assert detect_language(Path('test.ts')) == 'typescript'
assert detect_language(Path('test.rs')) == 'rust'
assert detect_language(Path('test.go')) == 'go'
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$LANG_TEST" == "ok" ]]; then
    log_pass "Language detection (py, js, ts, rs, go)"
else
    log_fail "Language detection"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Missing: ${#MISSING_DEPS[@]}"

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo ""
    echo "=== Missing Dependencies ==="
    echo "Run these commands to install missing components:"
    echo ""
    printf '%s\n' "${MISSING_DEPS[@]}" | sort -u | while read -r cmd; do
        echo "  $cmd"
    done
fi

echo ""
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL ($FAIL failures)"
    exit 1
elif [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo "Result: INCOMPLETE (missing dependencies)"
    exit 0
else
    echo "Result: PASS"
    exit 0
fi
