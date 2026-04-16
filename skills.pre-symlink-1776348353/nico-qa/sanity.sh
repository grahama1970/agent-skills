#!/usr/bin/env bash
# sanity.sh — Smoke test for the nico-qa skill
# Verifies imports, --help, and optionally runs audit if API is reachable.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== Nico QA Sanity Test ==="
echo ""

# 1. Check that nico_qa.py imports without error
echo "1. Import check"
if uv run python -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('nico_qa', '$SKILL_DIR/nico_qa.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)" 2>/dev/null; then
    pass "nico_qa.py imports cleanly"
else
    fail "nico_qa.py import failed"
fi

# 2. Check --help works
echo "2. CLI --help"
if uv run "$SKILL_DIR/nico_qa.py" --help >/dev/null 2>&1; then
    pass "nico_qa.py --help works"
else
    fail "nico_qa.py --help failed"
fi

# 3. Check audit --help
echo "3. Audit subcommand --help"
if uv run "$SKILL_DIR/nico_qa.py" audit --help >/dev/null 2>&1; then
    pass "audit --help works"
else
    fail "audit --help failed"
fi

# 4. Check report --help
echo "4. Report subcommand --help"
if uv run "$SKILL_DIR/nico_qa.py" report --help >/dev/null 2>&1; then
    pass "report --help works"
else
    fail "report --help failed"
fi

# 5. If API is reachable, run a live audit
echo "5. Live audit (optional — skipped if API unreachable)"
API_URL="${EXPLORER_API_URL:-http://localhost:3001}"
if curl -s --max-time 3 "$API_URL/api/health" >/dev/null 2>&1; then
    echo "   API reachable at $API_URL — running audit..."
    OUTPUT=$(uv run "$SKILL_DIR/nico_qa.py" audit 2>/dev/null || true)
    if echo "$OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'findings' in d" 2>/dev/null; then
        pass "audit returned valid JSON with findings"
    else
        fail "audit output is not valid JSON or missing 'findings'"
    fi
else
    echo "   API not reachable at $API_URL — skipping live audit"
    pass "(skipped — API offline)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
