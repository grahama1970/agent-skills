#!/usr/bin/env bash
# Sanity tests for clarify skill
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

echo "=== Clarify Skill Sanity Tests ==="
echo ""

# Add agent-skills directory to Python path for imports
export PYTHONPATH="$SCRIPT_DIR/..:${PYTHONPATH:-}"

# -----------------------------------------------------------------------------
# 1. Python imports
# -----------------------------------------------------------------------------
echo "1. Python imports"

if python3 -c "from clarify import ask, choose, ask_questions" 2>/dev/null; then
    log_pass "High-level API imports (ask, choose, ask_questions)"
else
    log_fail "High-level API imports"
fi

if python3 -c "from clarify import ClarifyQuestion, ClarifyOption" 2>/dev/null; then
    log_pass "Type imports (ClarifyQuestion, ClarifyOption)"
else
    log_fail "Type imports"
fi

if python3 -c "from clarify import ClarifyError, ClarifyTimeout" 2>/dev/null; then
    log_pass "Exception imports"
else
    log_fail "Exception imports"
fi

# -----------------------------------------------------------------------------
# 2. Dependencies
# -----------------------------------------------------------------------------
echo "2. Dependencies"

if python3 -c "import flask" 2>/dev/null; then
    log_pass "flask installed"
else
    log_missing "flask not installed" "pip install flask"
fi

if python3 -c "import werkzeug" 2>/dev/null; then
    log_pass "werkzeug installed"
else
    log_missing "werkzeug not installed" "pip install werkzeug"
fi

# -----------------------------------------------------------------------------
# 3. UI build
# -----------------------------------------------------------------------------
echo "3. UI build"

UI_DIST="$SCRIPT_DIR/ui/dist"
if [[ -d "$UI_DIST" ]]; then
    log_pass "UI dist directory exists"
    if [[ -f "$UI_DIST/index.html" ]]; then
        log_pass "UI index.html exists"
    else
        log_fail "UI index.html missing"
    fi
else
    log_missing "UI not built" "cd $SCRIPT_DIR/ui && npm install && npm run build"
fi

# -----------------------------------------------------------------------------
# 4. Question normalization
# -----------------------------------------------------------------------------
echo "4. Question normalization"

NORMALIZE_TEST=$(python3 -c "
from clarify import ClarifyQuestion
from clarify.runner import normalize_questions

# Test dict normalization
questions = normalize_questions([
    {'prompt': 'Test question'},
    {'prompt': 'Choice', 'kind': 'single-choice', 'options': [{'label': 'A'}, {'label': 'B'}]}
])
assert len(questions) == 2
assert isinstance(questions[0], ClarifyQuestion)
assert questions[0].prompt == 'Test question'
assert questions[1].kind == 'single-choice'
assert len(questions[1].options) == 2
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$NORMALIZE_TEST" == "ok" ]]; then
    log_pass "Question normalization"
else
    log_fail "Question normalization"
fi

# -----------------------------------------------------------------------------
# 5. Type validation
# -----------------------------------------------------------------------------
echo "5. Type validation"

TYPE_TEST=$(python3 -c "
from clarify import ClarifyQuestion, ClarifyOption

q = ClarifyQuestion(
    id='test',
    prompt='Test?',
    kind='single-choice',
    options=[
        ClarifyOption(id='a', label='Option A', description='First'),
        ClarifyOption(id='b', label='Option B'),
    ],
    docs_link='https://example.com',
    artifact_paths=['/path/to/file'],
    visual_assets=['/path/to/image.png'],
    required=True,
)
assert q.id == 'test'
assert len(q.options) == 2
assert q.options[0].description == 'First'
print('ok')
" 2>/dev/null || echo "fail")

if [[ "$TYPE_TEST" == "ok" ]]; then
    log_pass "ClarifyQuestion/ClarifyOption types"
else
    log_fail "ClarifyQuestion/ClarifyOption types"
fi

# -----------------------------------------------------------------------------
# 6. TUI availability
# -----------------------------------------------------------------------------
echo "6. TUI module"

if python3 -c "from clarify.tui import prompt_single_question" 2>/dev/null; then
    log_pass "TUI prompt_single_question import"
else
    log_fail "TUI module import"
fi

# -----------------------------------------------------------------------------
# 7. Server module
# -----------------------------------------------------------------------------
echo "7. Server module"

if python3 -c "from clarify.server import ClarifyServer" 2>/dev/null; then
    log_pass "ClarifyServer import"
else
    log_fail "ClarifyServer import"
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
