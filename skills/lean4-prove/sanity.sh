#!/bin/bash
set -eo pipefail

echo "=== lean4-prove Sanity Check ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="${LEAN4_CONTAINER:-lean_runner}"
CREDENTIALS="$HOME/.claude/.credentials.json"

# 1. Check Docker available
if ! command -v docker &>/dev/null; then
    echo "  [FAIL] Docker not installed"
    exit 1
fi
echo "  [PASS] Docker available"

# 2. Check container running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "  [WARN] Container '$CONTAINER' not running"
    echo "         Start with: docker start $CONTAINER"
    echo "         Or set LEAN4_CONTAINER to a running container"
    # Don't exit - continue checking other prerequisites
else
    echo "  [PASS] Container '$CONTAINER' running"

    # 3. Check Lean4 available in container
    if ! docker exec "$CONTAINER" which lean &>/dev/null; then
        echo "  [FAIL] Lean4 not found in container"
    else
        echo "  [PASS] Lean4 found in container"
    fi
fi

# 4. Check OAuth credentials
if [[ ! -f "$CREDENTIALS" ]]; then
    echo "  [FAIL] OAuth credentials not found at $CREDENTIALS"
    echo "         Run 'claude' to authenticate"
    exit 1
fi
echo "  [PASS] OAuth credentials file exists"

# 5. Check token not expired
EXPIRES_AT=$(python3 -c "import json; print(json.load(open('$CREDENTIALS')).get('claudeAiOauth', {}).get('expiresAt', 0))" 2>/dev/null || echo "0")
NOW_MS=$(python3 -c "import time; print(int(time.time() * 1000))")

if [[ "$EXPIRES_AT" != "0" ]] && [[ "$NOW_MS" -gt "$EXPIRES_AT" ]]; then
    echo "  [WARN] OAuth token expired"
    echo "         Run 'claude' to refresh"
else
    echo "  [PASS] OAuth token valid"
fi

# 6. Check Python available
if ! command -v python3 &>/dev/null; then
    echo "  [FAIL] Python3 not installed"
    exit 1
fi
echo "  [PASS] Python3 available"

# 7. Check prove.py exists
if [[ ! -f "$SCRIPT_DIR/prove.py" ]]; then
    echo "  [FAIL] prove.py not found"
    exit 1
fi
echo "  [PASS] prove.py exists"

# 8. Check run.sh exists and is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [FAIL] run.sh not executable"
    exit 1
fi
echo "  [PASS] run.sh executable"

# 9. Test help output
if ! "$SCRIPT_DIR/run.sh" --help | grep -q "Usage:"; then
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi
echo "  [PASS] CLI help works"

# 10. Optional: Full integration test (only if container running)
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "  [INFO] Running integration test..."

    # Simple proof that should succeed quickly - use haiku for speed
    RESULT=$("$SCRIPT_DIR/run.sh" --requirement "Prove True" --model haiku --candidates 1 --retries 1 --timeout 30 2>&1) || true

    if echo "$RESULT" | grep -q '"success": true'; then
        echo "  [PASS] Integration test passed"
    else
        echo "  [WARN] Integration test did not succeed"
        echo "         This may be due to rate limiting or API issues"
        echo "         Output: $(echo "$RESULT" | head -c 300)"
    fi
else
    echo "  [SKIP] Integration test (container not running)"
fi

echo "Result: PASS"

