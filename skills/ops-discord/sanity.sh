#!/usr/bin/env bash
# Discord Operations Skill - Sanity Check
# Verifies the modular architecture works correctly
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Discord Operations Sanity Check ==="
echo ""

# Track failures
FAILURES=0

# Helper functions
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; FAILURES=$((FAILURES + 1)); }

# -----------------------------------------------------------------------------
# 1. Check module structure
# -----------------------------------------------------------------------------
echo "--- Module Structure ---"

if [ -d "discord_ops" ]; then
    pass "discord_ops package directory exists"
else
    fail "discord_ops package directory missing"
fi

for module in config.py utils.py keyword_matcher.py graph_persistence.py webhook_monitor.py __init__.py; do
    if [ -f "discord_ops/$module" ]; then
        pass "discord_ops/$module exists"
    else
        fail "discord_ops/$module missing"
    fi
done

if [ -f "discord_ops.py" ]; then
    pass "CLI entry point discord_ops.py exists"
else
    fail "CLI entry point discord_ops.py missing"
fi

if [ -f "discord_ops_monolith.py" ]; then
    pass "Monolith backup discord_ops_monolith.py exists"
else
    fail "Monolith backup discord_ops_monolith.py missing"
fi

echo ""

# -----------------------------------------------------------------------------
# 2. Check line counts (all modules < 500 lines)
# -----------------------------------------------------------------------------
echo "--- Line Counts (< 500 each) ---"

MAX_LINES=500
for module in discord_ops/config.py discord_ops/utils.py discord_ops/keyword_matcher.py discord_ops/graph_persistence.py discord_ops/webhook_monitor.py; do
    lines=$(wc -l < "$module")
    if [ "$lines" -lt "$MAX_LINES" ]; then
        pass "$module: $lines lines"
    else
        fail "$module: $lines lines (exceeds $MAX_LINES)"
    fi
done

# CLI entry point can be slightly larger but still reasonable
cli_lines=$(wc -l < discord_ops.py)
if [ "$cli_lines" -lt 600 ]; then
    pass "discord_ops.py: $cli_lines lines"
else
    fail "discord_ops.py: $cli_lines lines (exceeds 600)"
fi

echo ""

# -----------------------------------------------------------------------------
# 3. Check imports work (no circular imports)
# -----------------------------------------------------------------------------
echo "--- Import Tests ---"

if python3 -c "from discord_ops.config import SKILL_DIR, DEFAULT_KEYWORDS" 2>/dev/null; then
    pass "config module imports"
else
    fail "config module import error"
fi

if python3 -c "from discord_ops.utils import load_config, RateLimiter, with_retries" 2>/dev/null; then
    pass "utils module imports"
else
    fail "utils module import error"
fi

if python3 -c "from discord_ops.keyword_matcher import KeywordMatch, match_keywords" 2>/dev/null; then
    pass "keyword_matcher module imports"
else
    fail "keyword_matcher module import error"
fi

if python3 -c "from discord_ops.graph_persistence import persist_match_to_memory, search_memory" 2>/dev/null; then
    pass "graph_persistence module imports"
else
    fail "graph_persistence module import error"
fi

if python3 -c "from discord_ops.webhook_monitor import get_feature_status, is_monitor_running" 2>/dev/null; then
    pass "webhook_monitor module imports"
else
    fail "webhook_monitor module import error"
fi

# Test full import chain (catches circular imports)
if python3 -c "
from discord_ops.config import SKILL_DIR
from discord_ops.keyword_matcher import KeywordMatch
from discord_ops.utils import load_config
from discord_ops.graph_persistence import log_match
from discord_ops.webhook_monitor import run_monitor
print('Full import chain OK')
" 2>/dev/null; then
    pass "No circular imports detected"
else
    fail "Circular import detected"
fi

echo ""

# -----------------------------------------------------------------------------
# 4. CLI functionality tests
# -----------------------------------------------------------------------------
echo "--- CLI Tests ---"

if python3 discord_ops.py --help > /dev/null 2>&1; then
    pass "CLI --help works"
else
    fail "CLI --help failed"
fi

if python3 discord_ops.py version > /dev/null 2>&1; then
    pass "CLI version command works"
else
    fail "CLI version command failed"
fi

if python3 discord_ops.py keywords list > /dev/null 2>&1; then
    pass "CLI keywords list works"
else
    fail "CLI keywords list failed"
fi

if python3 discord_ops.py guild list > /dev/null 2>&1; then
    pass "CLI guild list works"
else
    fail "CLI guild list failed"
fi

if python3 discord_ops.py webhook list > /dev/null 2>&1; then
    pass "CLI webhook list works"
else
    fail "CLI webhook list failed"
fi

if python3 discord_ops.py monitor status > /dev/null 2>&1; then
    pass "CLI monitor status works"
else
    fail "CLI monitor status failed"
fi

if python3 discord_ops.py memory status > /dev/null 2>&1; then
    pass "CLI memory status works"
else
    fail "CLI memory status failed"
fi

echo ""

# -----------------------------------------------------------------------------
# 5. Unit test: KeywordMatch
# -----------------------------------------------------------------------------
echo "--- Unit Tests ---"

if python3 -c "
from discord_ops.keyword_matcher import KeywordMatch, match_keywords

# Test keyword matching
patterns = [r'CVE-\d{4}-\d+', r'exploit']
matches = match_keywords('Found CVE-2024-1234 exploit!', patterns)
assert 'CVE-\\d{4}-\\d+' in matches, 'CVE pattern should match'
assert 'exploit' in matches, 'exploit should match'

# Test KeywordMatch dataclass
m = KeywordMatch.create_test_match()
assert m.guild_name == 'Test Server'
d = m.to_dict()
assert 'content' in d
assert 'matched_keywords' in d

# Test from_dict roundtrip
m2 = KeywordMatch.from_dict(d)
assert m2.content == m.content

print('KeywordMatch tests passed')
" 2>&1; then
    pass "KeywordMatch unit tests"
else
    fail "KeywordMatch unit tests failed"
fi

if python3 -c "
from discord_ops.utils import RateLimiter
import time

# Test rate limiter
rl = RateLimiter(requests_per_second=100)  # Fast for testing
start = time.time()
rl.acquire()
rl.acquire()
elapsed = time.time() - start
assert elapsed >= 0.01, 'Rate limiter should delay'
print('RateLimiter tests passed')
" 2>&1; then
    pass "RateLimiter unit tests"
else
    fail "RateLimiter unit tests failed"
fi

echo ""

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo "=== Summary ==="
if [ "$FAILURES" -eq 0 ]; then
    echo "[SUCCESS] All sanity checks passed!"
    exit 0
else
    echo "[FAILURE] $FAILURES check(s) failed"
    exit 1
fi
