#!/usr/bin/env bash
# Sanity tests for memory skill
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

echo "=== Memory Skill Sanity Tests ==="
echo ""

# -----------------------------------------------------------------------------
# 1. CLI availability
# -----------------------------------------------------------------------------
echo "1. CLI availability"

if command -v memory-agent &>/dev/null; then
    log_pass "memory-agent CLI found"
    # Detect Python from memory-agent's shebang or entry point
    MEMORY_AGENT_PATH=$(command -v memory-agent)
    MEMORY_PYTHON=$(head -1 "$MEMORY_AGENT_PATH" 2>/dev/null | sed 's/^#!//' | tr -d ' ' || echo "")
    if [[ -z "$MEMORY_PYTHON" ]] || [[ ! -x "$MEMORY_PYTHON" ]]; then
        # Fallback: find python in same bin dir as memory-agent
        MEMORY_PYTHON="$(dirname "$MEMORY_AGENT_PATH")/python"
    fi
    if [[ ! -x "$MEMORY_PYTHON" ]]; then
        MEMORY_PYTHON="$MEMORY_PYTHON"  # Last resort fallback
    fi
else
    log_fail "memory-agent CLI not found"
    echo "       Install: pip install -e /path/to/memory"
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. Help commands work
# -----------------------------------------------------------------------------
echo "2. Help commands"

if memory-agent --help &>/dev/null; then
    log_pass "memory-agent --help"
else
    log_fail "memory-agent --help"
fi

# Test that documented commands exist
COMMANDS=(
    "search"
    "recall"
    "recall-diff"
    "related"
    "multihop"
    "add-episode"
    "list-episodes"
    "add-edge"
    "approve-edge"
    "explain"
    "feedback"
    "build-relationships"
    "build-relationships-llm"
    "agent-request-add"
    "agent-request-list"
    "agent-request-ack"
    "workspace-detect"
    "workspace-ingest"
    "workspace-build"
    "prove"
    "prove-pending"
    "prove-status"
    "proof-worker"
)

echo "3. Documented commands exist"
for cmd in "${COMMANDS[@]}"; do
    if memory-agent "$cmd" --help &>/dev/null; then
        log_pass "$cmd --help"
    else
        log_fail "$cmd --help"
    fi
done

# -----------------------------------------------------------------------------
# 4. Output validation (requires DB for search)
# -----------------------------------------------------------------------------
echo "4. Output format validation"

# Test search returns expected structure (may be JSON or Python repr)
OUTPUT=$(memory-agent search --q "test" --scope "test" --k 1 2>&1 || echo "error")
if echo "$OUTPUT" | grep -q "'meta'" || echo "$OUTPUT" | grep -q '"meta"'; then
    if echo "$OUTPUT" | grep -q "'items'" || echo "$OUTPUT" | grep -q '"items"'; then
        log_pass "search returns meta/items structure"
    else
        log_fail "search missing 'items' in output"
    fi
else
    # Check if it's a connection error vs missing keys
    if echo "$OUTPUT" | grep -qi "error\|exception\|connection"; then
        log_missing "search (DB connection issue)" "Ensure ArangoDB is running and ARANGO_URL is set"
    else
        log_fail "search missing 'meta' in output"
    fi
fi

# Test prove --local-only (no LLM or DB needed)
OUTPUT=$(memory-agent prove --claim "For all n, n + 0 = n" --local-only 2>&1 || echo "error")
if echo "$OUTPUT" | grep -q "likely_provable\|score"; then
    log_pass "prove --local-only returns provability score"
else
    log_fail "prove --local-only format invalid"
fi

# -----------------------------------------------------------------------------
# 5. Python API availability
# -----------------------------------------------------------------------------
echo "5. Python API"

if $MEMORY_PYTHON -c "from graph_memory.api import MemoryClient" 2>/dev/null; then
    log_pass "MemoryClient import"
else
    log_fail "MemoryClient import"
fi

if $MEMORY_PYTHON -c "from graph_memory.api import MemoryClient; c = MemoryClient(); assert hasattr(c, 'search')" 2>/dev/null; then
    log_pass "MemoryClient.search exists"
else
    log_fail "MemoryClient.search missing"
fi

if $MEMORY_PYTHON -c "from graph_memory.api import MemoryClient; c = MemoryClient(); assert hasattr(c, 'assess_provability')" 2>/dev/null; then
    log_pass "MemoryClient.assess_provability exists"
else
    log_fail "MemoryClient.assess_provability missing"
fi

if $MEMORY_PYTHON -c "from graph_memory.api import MemoryClient; c = MemoryClient(); assert hasattr(c, 'get')" 2>/dev/null; then
    log_pass "MemoryClient.get exists"
else
    log_fail "MemoryClient.get missing"
fi

# -----------------------------------------------------------------------------
# 6. Proof assessment module
# -----------------------------------------------------------------------------
echo "6. Proof assessment module"

if $MEMORY_PYTHON -c "from graph_memory.integrations.proof_assessment import likely_provable, get_provability_score" 2>/dev/null; then
    log_pass "proof_assessment imports"
else
    log_fail "proof_assessment imports"
fi

# Test Tier 1 classifier works
TIER1_TEST=$($MEMORY_PYTHON -c "
from graph_memory.integrations.proof_assessment import likely_provable
assert likely_provable('For all n, n + 0 = n') == True
assert likely_provable('restart the server') == False
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$TIER1_TEST" == "ok" ]]; then
    log_pass "Tier 1 classifier (local regex)"
else
    log_fail "Tier 1 classifier"
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
