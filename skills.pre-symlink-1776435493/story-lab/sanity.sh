#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

check() {
    if eval "$2" &>/dev/null; then
        echo "PASS: $1"
        ((PASS++))
    else
        echo "FAIL: $1"
        ((FAIL++))
    fi
}

echo "=== story-lab sanity ==="

# --- Structural checks ---
check "SKILL.md exists" "test -f ${SCRIPT_DIR}/SKILL.md"
check "run.sh exists and is executable" "test -x ${SCRIPT_DIR}/run.sh"
check "run.sh outputs SPECIFICATION ONLY" "${SCRIPT_DIR}/run.sh 2>&1 | grep -q 'SPECIFICATION ONLY'"
check "SKILL.md has triggers" "grep -q 'triggers:' ${SCRIPT_DIR}/SKILL.md"
check "SKILL.md composes create-story" "grep -q 'create-story' ${SCRIPT_DIR}/SKILL.md"
check "SKILL.md composes review-story" "grep -q 'review-story' ${SCRIPT_DIR}/SKILL.md"
check "SKILL.md composes memory" "grep -q 'memory' ${SCRIPT_DIR}/SKILL.md"

# --- converge.py checks ---
check "converge.py exists" "test -f ${SCRIPT_DIR}/converge.py"
check "pyproject.toml exists" "test -f ${SCRIPT_DIR}/pyproject.toml"

# Python import check
check "converge.py imports work" \
    "cd ${SCRIPT_DIR} && uv run --project '${SCRIPT_DIR}' python -c 'from converge import app; print(\"ok\")'"

# Help output checks
HELP_OUTPUT=$(uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/converge.py" --help 2>/dev/null || true)

check "converge --help shows converge command" \
    "echo '${HELP_OUTPUT}' | grep -q 'converge'"

CONVERGE_HELP=$(uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/converge.py" converge --help 2>/dev/null || true)

check "converge command has --input" \
    "echo '${CONVERGE_HELP}' | grep -q '\-\-input'"
check "converge command has --out" \
    "echo '${CONVERGE_HELP}' | grep -q '\-\-out'"
check "converge command has --max-rounds" \
    "echo '${CONVERGE_HELP}' | grep -q '\-\-max-rounds'"

# Dry-run convergence loop
OUT_DIR=$(mktemp -d)
FIXTURE=$(mktemp --suffix=.md)
echo "# Test lyrics\nVerse one line one\nVerse one line two" > "${FIXTURE}"

check "dry-run converge completes" \
    "uv run --project '${SCRIPT_DIR}' python '${SCRIPT_DIR}/converge.py' converge \
        --input '${FIXTURE}' \
        --out '${OUT_DIR}' \
        --max-rounds 2 \
        --dry-run"

check "loop_results.json produced" "test -f ${OUT_DIR}/loop_results.json"

check "loop_results.json has rounds" \
    "python3 -c \"import json; d=json.load(open('${OUT_DIR}/loop_results.json')); assert len(d['rounds']) > 0\""

check "loop_results.json has weights" \
    "python3 -c \"import json; d=json.load(open('${OUT_DIR}/loop_results.json')); assert 'weights' in d\""

rm -rf "${OUT_DIR}" "${FIXTURE}"

# Composed skills exist
MISSING=0
for skill in create-story review-story; do
    if [[ ! -d "$(dirname "$SCRIPT_DIR")/${skill}" ]]; then
        MISSING=$((MISSING + 1))
    fi
done
if [[ $MISSING -eq 0 ]]; then
    echo "PASS: composed skills exist (create-story, review-story)"
    ((PASS++))
else
    echo "FAIL: ${MISSING} composed skill(s) missing"
    ((FAIL++))
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
exit $FAIL
