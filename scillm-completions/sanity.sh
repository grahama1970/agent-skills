#!/usr/bin/env bash
# Sanity tests for scillm-completions skill
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

echo "=== scillm Completions Skill Sanity Tests ==="
echo ""

# -----------------------------------------------------------------------------
# 1. Package availability
# -----------------------------------------------------------------------------
echo "1. Package availability"

if python3 -c "import scillm" 2>/dev/null; then
    log_pass "scillm package installed"
else
    log_missing "scillm package not found" "pip install scillm"
fi

# -----------------------------------------------------------------------------
# 2. Paved API imports
# -----------------------------------------------------------------------------
echo "2. Paved API imports"

IMPORTS=("chat" "chat_json" "analyze_image" "analyze_image_json")

for func in "${IMPORTS[@]}"; do
    if python3 -c "from scillm.paved import $func" 2>/dev/null; then
        log_pass "scillm.paved.$func"
    else
        log_fail "scillm.paved.$func not importable"
    fi
done

# -----------------------------------------------------------------------------
# 3. Batch API imports
# -----------------------------------------------------------------------------
echo "3. Batch API imports"

if python3 -c "from scillm.batch import parallel_acompletions_iter" 2>/dev/null; then
    log_pass "parallel_acompletions_iter import"
else
    log_fail "parallel_acompletions_iter import"
fi

# -----------------------------------------------------------------------------
# 4. Function signatures
# -----------------------------------------------------------------------------
echo "4. Function signatures"

SIG_CHECK=$(python3 -c "
import inspect
from scillm.paved import chat, chat_json, analyze_image

# chat should accept prompt
sig = inspect.signature(chat)
params = list(sig.parameters.keys())
assert 'prompt' in params or len(params) > 0

# chat_json should accept prompt
sig = inspect.signature(chat_json)
params = list(sig.parameters.keys())
assert 'prompt' in params or len(params) > 0

# analyze_image should accept image and prompt
sig = inspect.signature(analyze_image)
params = list(sig.parameters.keys())
assert len(params) >= 2

print('ok')
" 2>/dev/null || echo "fail")

if [[ "$SIG_CHECK" == "ok" ]]; then
    log_pass "Function signatures valid"
else
    log_fail "Function signatures invalid"
fi

# -----------------------------------------------------------------------------
# 5. Environment check
# -----------------------------------------------------------------------------
echo "5. Environment"

if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    log_pass "OPENROUTER_API_KEY set"
else
    log_missing "OPENROUTER_API_KEY not set" "export OPENROUTER_API_KEY=sk-or-..."
fi

# -----------------------------------------------------------------------------
# 6. Async compatibility
# -----------------------------------------------------------------------------
echo "6. Async compatibility"

ASYNC_CHECK=$(python3 -c "
import asyncio
from scillm.paved import chat
assert asyncio.iscoroutinefunction(chat), 'chat should be async'
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$ASYNC_CHECK" == "ok" ]]; then
    log_pass "chat is async function"
else
    log_fail "chat async check"
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
