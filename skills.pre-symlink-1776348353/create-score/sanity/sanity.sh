#!/usr/bin/env bash
#
# Fast sanity check for create-score skill
# No GPU required - checks syntax, imports, CLI help
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== create-score Sanity Check (Fast) ==="
echo ""

PASSED=0
FAILED=0

pass() {
    echo "[PASS] $1"
    ((PASSED++)) || true
}

fail() {
    echo "[FAIL] $1"
    ((FAILED++)) || true
}

warn() {
    echo "[WARN] $1"
}

# 1. Check Python syntax
echo -n "[1/5] Python syntax... "
if python -m py_compile "${SKILL_DIR}/create_score/cli.py" \
   && python -m py_compile "${SKILL_DIR}/create_score/schemas.py" \
   && python -m py_compile "${SKILL_DIR}/create_score/docker_manager.py" \
   && python -m py_compile "${SKILL_DIR}/create_score/http_client.py" \
   && python -m py_compile "${SKILL_DIR}/create_score/bridge_prompts.py" \
   && python -m py_compile "${SKILL_DIR}/create_score/__init__.py"; then
    pass "Python syntax OK"
else
    fail "Python syntax errors"
fi

# 2. Check dependencies can import
echo -n "[2/5] Dependencies... "
if uv run --project "${SKILL_DIR}" python -c "
import typer
import httpx
import pydantic
from loguru import logger
print('OK')
" 2>/dev/null | grep -q "OK"; then
    pass "Dependencies OK"
else
    fail "Dependencies missing"
fi

# 3. Check CLI help works
echo -n "[3/5] CLI help... "
if uv run --project "${SKILL_DIR}" python -m create_score.cli --help > /dev/null 2>&1; then
    pass "CLI help OK"
else
    fail "CLI help failed"
fi

# 4. Check subcommands registered
echo -n "[4/5] Subcommands... "
HELP_OUTPUT=$(uv run --project "${SKILL_DIR}" python -m create_score.cli --help 2>&1)
ALL_FOUND=true
for cmd in up down generate status; do
    if ! echo "$HELP_OUTPUT" | grep -q "$cmd"; then
        fail "Missing command '$cmd'"
        ALL_FOUND=false
    fi
done
if $ALL_FOUND; then
    pass "All subcommands registered"
fi

# 5. Check Docker/compose available (optional)
echo -n "[5/5] Docker/compose... "
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    pass "Docker/compose available"
else
    warn "Docker/compose not available (optional for sanity-full)"
fi

# Summary
echo ""
echo "=== Summary ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -gt 0 ]; then
    echo "SANITY CHECK FAILED"
    exit 1
else
    echo "SANITY CHECK PASSED"
    exit 0
fi
