#!/usr/bin/env bash
# Sanity check for ops-nzbgeek skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0; FAIL=0; SKIP=0

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
skip() { echo "  [SKIP] $1 (service unavailable)"; SKIP=$((SKIP + 1)); }

echo "=== Sanity check for ops-nzbgeek ==="

# --- Local checks (hard fail) ---

# Check SKILL.md exists
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    pass "SKILL.md exists"
else
    fail "SKILL.md not found"
fi

# Check run.sh exists and is executable
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    pass "run.sh exists and is executable"
else
    fail "run.sh not found or not executable"
fi

# Check sanity scripts exist
if [[ -x "$SCRIPT_DIR/sanity/nzbgeek-api.sh" ]]; then
    pass "sanity/nzbgeek-api.sh exists"
else
    fail "sanity/nzbgeek-api.sh not found or not executable"
fi

if [[ -x "$SCRIPT_DIR/sanity/sabnzbd-api.sh" ]]; then
    pass "sanity/sabnzbd-api.sh exists"
else
    fail "sanity/sabnzbd-api.sh not found or not executable"
fi

# Check run.sh help works
if "$SCRIPT_DIR/run.sh" help >/dev/null 2>&1; then
    pass "run.sh help works"
else
    fail "run.sh help failed"
fi

# Check Python modules exist
if [[ -f "$SCRIPT_DIR/ops_nzbgeek/__init__.py" ]]; then
    pass "ops_nzbgeek/__init__.py exists"
else
    fail "ops_nzbgeek/__init__.py not found"
fi

for module in cli search download status interview_helper monitor_helper; do
    if [[ -f "$SCRIPT_DIR/ops_nzbgeek/$module.py" ]]; then
        pass "ops_nzbgeek/$module.py exists"
    else
        fail "ops_nzbgeek/$module.py not found"
    fi
done

# Check Python module imports
cd "$SCRIPT_DIR"
if uv run python -c "
from ops_nzbgeek.search import search_nzb
from ops_nzbgeek.download import add_nzb
from ops_nzbgeek.status import get_queue
from ops_nzbgeek.interview_helper import handle_multiple_results
from ops_nzbgeek.monitor_helper import register_download
print('All modules import successfully')
" 2>/dev/null; then
    pass "All Python modules import successfully"
else
    fail "Python module imports failed"
fi

# Check CLI help
if uv run python -m ops_nzbgeek.cli --help >/dev/null 2>&1; then
    pass "CLI --help works"
else
    fail "CLI --help failed"
fi

# --- External service checks (graceful skip) ---

# NZBGeek API check
echo ""
echo "  [INFO] Testing NZBGeek API connectivity..."
if timeout 15 "$SCRIPT_DIR/sanity/nzbgeek-api.sh" >/dev/null 2>&1; then
    pass "NZBGeek API is reachable"
else
    skip "NZBGeek API connectivity (API down or key missing)"
fi

# SABnzbd API check
echo "  [INFO] Testing SABnzbd API connectivity..."
if timeout 15 "$SCRIPT_DIR/sanity/sabnzbd-api.sh" >/dev/null 2>&1; then
    pass "SABnzbd API is reachable"
else
    skip "SABnzbd API connectivity (service down or key missing)"
fi

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed, $SKIP skipped ==="
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL"
    exit 1
fi
echo "Result: PASS"
exit 0
