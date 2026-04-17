#!/usr/bin/env bash
# music-lab sanity checks — real-world, not mocked
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRORS=0

echo "=== music-lab sanity ==="

# 1. Python imports work
echo -n "  converge.py imports... "
if uv run --project "${SCRIPT_DIR}" python -c "from converge import app; print('ok')" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL"
    ERRORS=$((ERRORS + 1))
fi

# 2. SKILL.md has triggers
echo -n "  SKILL.md triggers... "
if grep -q "triggers:" "${SCRIPT_DIR}/SKILL.md"; then
    echo "PASS"
else
    echo "FAIL"
    ERRORS=$((ERRORS + 1))
fi

# 3. Dry-run converge with Whisperheads fixture
FIXTURE_DIR="$(dirname "$SCRIPT_DIR")/create-music/fixtures/whisperheads"
echo -n "  dry-run converge... "
if [[ -f "${FIXTURE_DIR}/piano-roll-spec.json" ]] && [[ -f "${FIXTURE_DIR}/annotated-lyrics.json" ]]; then
    OUT_DIR=$(mktemp -d)
    if uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/converge.py" converge \
        --spec "${FIXTURE_DIR}/piano-roll-spec.json" \
        --lyrics "${FIXTURE_DIR}/annotated-lyrics.json" \
        --out "${OUT_DIR}" \
        --dry-run 2>/dev/null; then
        echo "PASS"
    else
        echo "FAIL"
        ERRORS=$((ERRORS + 1))
    fi
    rm -rf "$OUT_DIR"
else
    echo "SKIP (fixtures not found)"
fi

# 4. Composed skills exist
echo -n "  composed skills exist... "
MISSING=0
for skill in create-music review-music; do
    if [[ ! -d "$(dirname "$SCRIPT_DIR")/${skill}" ]]; then
        MISSING=$((MISSING + 1))
    fi
done
if [[ $MISSING -eq 0 ]]; then
    echo "PASS"
else
    echo "FAIL (${MISSING} missing)"
    ERRORS=$((ERRORS + 1))
fi

echo "=== ${ERRORS} errors ==="
exit $ERRORS
