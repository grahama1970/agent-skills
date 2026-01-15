#!/bin/bash
# Quality Gate - Prevents lazy early exit
#
# Catches obvious errors Claude is trying to ignore.
# General - works on any project by detecting type.
#
# Config:
#   QUALITY_GATE_DISABLED=1  - Skip entirely
#   QUALITY_GATE_TIMEOUT=60  - Test timeout in seconds (default: 60)

[[ "${QUALITY_GATE_DISABLED:-0}" == "1" ]] && exit 0

# Resolve script directory for loading prompt
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/prompts/quality-gate.md"

# Read hook input
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null || echo ".")
cd "$CWD" || exit 0

# State tracking (use temp-ish location, not mixed with config)
STATE_DIR="${TMPDIR:-/tmp}/claude-quality-gate"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/$(echo "$CWD" | md5sum | cut -d' ' -f1)"

RETRIES=0
[[ -f "$STATE_FILE" ]] && RETRIES=$(cat "$STATE_FILE")
MAX_RETRIES=3
TIMEOUT="${QUALITY_GATE_TIMEOUT:-60}"

# Detect project type and set check command
CHECK_CMD=""

if [[ -f "Makefile" ]]; then
    # Check for specific targets
    if grep -q "^smokes-cli:" Makefile 2>/dev/null; then
        CHECK_CMD="timeout ${TIMEOUT}s make smokes-cli"
    elif grep -q "^smokes:" Makefile 2>/dev/null; then
        CHECK_CMD="timeout ${TIMEOUT}s make smokes"
    elif grep -q "^test:" Makefile 2>/dev/null; then
        CHECK_CMD="timeout ${TIMEOUT}s make test"
    fi
fi

# Python project detection
if [[ -z "$CHECK_CMD" ]] && { [[ -f "pyproject.toml" ]] || [[ -f "setup.py" ]] || [[ -f "requirements.txt" ]]; }; then
    if [[ -d "tests" ]] || [[ -d "test" ]]; then
        # Prefer uv if available, fall back to python -m pytest
        if command -v uv &>/dev/null; then
            CHECK_CMD="timeout ${TIMEOUT}s uv run pytest -q -x --tb=short 2>&1 | tail -30"
        else
            CHECK_CMD="timeout ${TIMEOUT}s python -m pytest -q -x --tb=short 2>&1 | tail -30"
        fi
    else
        # At minimum check imports
        PKG=$(find src -name "__init__.py" -path "*/src/*" 2>/dev/null | head -1 | sed 's|src/||;s|/__init__.py||;s|/|.|g')
        [[ -n "$PKG" ]] && CHECK_CMD="python -c 'import $PKG'"
    fi
fi

# Node.js detection
if [[ -z "$CHECK_CMD" ]] && [[ -f "package.json" ]]; then
    if grep -q '"test"' package.json 2>/dev/null; then
        CHECK_CMD="timeout ${TIMEOUT}s npm test 2>&1 | tail -30"
    fi
fi

# Go detection
if [[ -z "$CHECK_CMD" ]] && [[ -f "go.mod" ]]; then
    CHECK_CMD="timeout ${TIMEOUT}s go build ./... && timeout ${TIMEOUT}s go test ./... 2>&1 | tail -30"
fi

# Rust detection
if [[ -z "$CHECK_CMD" ]] && [[ -f "Cargo.toml" ]]; then
    CHECK_CMD="timeout ${TIMEOUT}s cargo check 2>&1 | tail -30"
fi

# Run checks if we have a command
RESULT=""
EXIT_CODE=0
if [[ -n "$CHECK_CMD" ]]; then
    echo "Quality gate: $CHECK_CMD" >&2
    RESULT=$(eval "$CHECK_CMD" 2>&1) || EXIT_CODE=$?
fi

# Comprehensive error patterns
ERROR_PATTERNS="(Error:|Exception:|FAILED|error\[E|SyntaxError|ImportError|ModuleNotFoundError|TypeError|ValueError|AttributeError|KeyError|AssertionError|RuntimeError|panic:|FATAL|npm ERR!|ENOENT|EACCES|failed to compile|cannot find)"

HAS_ERRORS=0
if [[ $EXIT_CODE -ne 0 ]]; then
    HAS_ERRORS=1
elif [[ -n "$RESULT" ]] && echo "$RESULT" | grep -qE "$ERROR_PATTERNS"; then
    HAS_ERRORS=1
fi

# Pass - clean exit
if [[ $HAS_ERRORS -eq 0 ]]; then
    rm -f "$STATE_FILE"
    echo "Quality gate: PASS" >&2
    exit 0
fi

# Fail - increment retries
RETRIES=$((RETRIES + 1))
echo "$RETRIES" > "$STATE_FILE"

# Load and render prompt from markdown file
render_prompt() {
    local template
    if [[ -f "$PROMPT_FILE" ]]; then
        template=$(cat "$PROMPT_FILE")
    else
        # Fallback if prompt file missing
        template="# Quality Gate BLOCKED\n\nFix the errors before stopping.\n\n\`\`\`\n{{OUTPUT}}\n\`\`\`\n\nAttempt {{ATTEMPT}}/{{MAX_ATTEMPTS}}"
    fi

    # Simple template substitution
    template="${template//\{\{OUTPUT\}\}/$RESULT}"
    template="${template//\{\{ATTEMPT\}\}/$RETRIES}"
    template="${template//\{\{MAX_ATTEMPTS\}\}/$MAX_RETRIES}"

    # Handle conditional for final attempt
    if [[ $RETRIES -ge $MAX_RETRIES ]]; then
        template="${template//\{\{#if FINAL_ATTEMPT\}\}/}"
        template="${template//\{\{\/if\}\}/}"
    else
        # Remove the final attempt block if not final
        template=$(echo "$template" | sed '/{{#if FINAL_ATTEMPT}}/,/{{\/if}}/d')
    fi

    echo "$template"
}

echo "" >&2
echo "========================================" >&2
render_prompt >&2
echo "========================================" >&2

# Clean up state after max retries
[[ $RETRIES -ge $MAX_RETRIES ]] && rm -f "$STATE_FILE"

exit 2
