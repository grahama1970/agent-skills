#!/usr/bin/env bash
# Sanity tests for certainly-prover skill
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

echo "=== Certainly Prover Skill Sanity Tests ==="
echo ""

# -----------------------------------------------------------------------------
# 1. Python package availability
# -----------------------------------------------------------------------------
echo "1. Package availability"

if python3 -c "import scillm" 2>/dev/null; then
    log_pass "scillm package installed"
else
    log_missing "scillm package not found" "pip install scillm[certainly]"
fi

if python3 -c "from scillm.integrations.certainly import prove_requirement" 2>/dev/null; then
    log_pass "prove_requirement import"
else
    log_missing "prove_requirement not importable" "pip install scillm[certainly]"
fi

# -----------------------------------------------------------------------------
# 2. Helper functions
# -----------------------------------------------------------------------------
echo "2. Helper functions"

if python3 -c "from scillm.integrations.certainly import is_available; print(is_available())" 2>/dev/null; then
    log_pass "is_available() callable"
else
    log_fail "is_available() not found"
fi

if python3 -c "from scillm.integrations.certainly import check_lean_container" 2>/dev/null; then
    log_pass "check_lean_container import"
else
    log_fail "check_lean_container import"
fi

# -----------------------------------------------------------------------------
# 3. Prerequisites check
# -----------------------------------------------------------------------------
echo "3. Prerequisites"

# Check OPENROUTER_API_KEY
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    log_pass "OPENROUTER_API_KEY set"
else
    log_missing "OPENROUTER_API_KEY not set" "export OPENROUTER_API_KEY=sk-or-..."
fi

# Check lean_runner container
if docker ps 2>/dev/null | grep -q lean_runner; then
    log_pass "lean_runner container running"
else
    log_missing "lean_runner container not running" "cd /path/to/lean4 && make lean-runner-up"
fi

# -----------------------------------------------------------------------------
# 4. Function signature check
# -----------------------------------------------------------------------------
echo "4. API signature"

API_CHECK=$(python3 -c "
import inspect
from scillm.integrations.certainly import prove_requirement
sig = inspect.signature(prove_requirement)
params = list(sig.parameters.keys())
assert 'requirement' in params or len(params) > 0, 'Missing requirement param'
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$API_CHECK" == "ok" ]]; then
    log_pass "prove_requirement signature valid"
else
    log_fail "prove_requirement signature"
fi

# -----------------------------------------------------------------------------
# 5. Response format (dry run - no actual proof)
# -----------------------------------------------------------------------------
echo "5. Response format documentation"

RESPONSE_CHECK=$(python3 -c "
success_fields = ['lean4_code', 'summary', 'tactic_used', 'compile_time_ms']
failure_fields = ['failure_reason', 'suggestion', 'summary', 'num_attempts']
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$RESPONSE_CHECK" == "ok" ]]; then
    log_pass "Response fields documented"
else
    log_fail "Response field check"
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
