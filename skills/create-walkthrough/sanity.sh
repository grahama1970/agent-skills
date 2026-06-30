#!/usr/bin/env bash
# Sanity check for /create-walkthrough skill.
# Verifies: imports, CLI help, extract-only on a test document.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"

PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

PASS=0
FAIL=0

check() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $label"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== create-walkthrough sanity ==="

# 1. Python imports
check "imports" "$PYTHON" -c "import sys; sys.path.insert(0, '$SKILL_DIR'); from walkthrough import extract_claims, verify_claims, Verdict, VerificationReport"

# 2. CLI help
check "cli-help" "$PYTHON" "$SKILL_DIR/walkthrough.py" --help

# 3. verify --help
check "verify-help" "$PYTHON" "$SKILL_DIR/walkthrough.py" verify --help

# 4. template --help
check "template-help" "$PYTHON" "$SKILL_DIR/walkthrough.py" template --help

# 5. Extract claims from a minimal test doc (basic types)
TMPFILE=$(mktemp /tmp/walkthrough_sanity_XXXXXX.md)
cat > "$TMPFILE" <<'EOF'
# Test Walkthrough

**File:** `${HOME}/workspace/experiments/pi-mono/.pi/skills/create-walkthrough/walkthrough.py` (500 lines)

The `extract_claims()` function on line 156 handles extraction.

Port 8602 is used by the embedding service.
EOF

check "extract-basic" "$PYTHON" "$SKILL_DIR/walkthrough.py" verify --file "$TMPFILE" --extract-only

# 5b. Extract claims from a doc with new claim types (collections, fields, classes, imports)
TMPFILE2=$(mktemp /tmp/walkthrough_sanity_v2_XXXXXX.md)
cat > "$TMPFILE2" <<'EOF'
# Test Walkthrough v2

Stored in the `user_priors` collection in ArangoDB.

The `participants` field tracks who was in the conversation.

New `Participants` TypedDict added to taxonomy.

`from analysis_llm import profile_user_from_session`

See `common/taxonomy_types.py` for the definition.
EOF

CLAIMS_OUTPUT=$("$PYTHON" "$SKILL_DIR/walkthrough.py" verify --file "$TMPFILE2" --extract-only 2>&1)
# Check that at least 4 claims were extracted (collection, field, class, import)
CLAIM_COUNT=$(echo "$CLAIMS_OUTPUT" | grep -c "^\s*\[")
if [ "$CLAIM_COUNT" -ge 4 ]; then
    echo "PASS: extract-new-types ($CLAIM_COUNT claims from v2 doc)"
    PASS=$((PASS + 1))
else
    echo "FAIL: extract-new-types (expected >=4 claims, got $CLAIM_COUNT)"
    FAIL=$((FAIL + 1))
fi

# 6. Full verify (expect exit 0 or 2 — not 1 which means crash)
set +e
"$PYTHON" "$SKILL_DIR/walkthrough.py" verify --file "$TMPFILE" >/dev/null 2>&1
RC=$?
set -e
if [ "$RC" -eq 0 ] || [ "$RC" -eq 2 ]; then
    echo "PASS: verify-runs (exit=$RC)"
    PASS=$((PASS + 1))
else
    echo "FAIL: verify-runs (exit=$RC — expected 0 or 2)"
    FAIL=$((FAIL + 1))
fi

# 7. Template generation
TMPL_OUT=$(mktemp /tmp/walkthrough_template_XXXXXX.md)
check "template-gen" "$PYTHON" "$SKILL_DIR/walkthrough.py" template --file "$SKILL_DIR/walkthrough.py" --output "$TMPL_OUT"

# 8. Template file has content
if [ -s "$TMPL_OUT" ]; then
    echo "PASS: template-has-content"
    PASS=$((PASS + 1))
else
    echo "FAIL: template-has-content"
    FAIL=$((FAIL + 1))
fi

# 9. References template exists
if [ -f "$SKILL_DIR/references/walkthrough_template.md" ]; then
    echo "PASS: references-template-exists"
    PASS=$((PASS + 1))
else
    echo "FAIL: references-template-exists"
    FAIL=$((FAIL + 1))
fi

# Cleanup
rm -f "$TMPFILE" "$TMPFILE2" "$TMPL_OUT"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
