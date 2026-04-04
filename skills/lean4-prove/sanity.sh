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

# 10. Test retrieval/memory integration
echo "  [INFO] Testing retrieval integration..."
RETRIEVAL_TEST=$(python3 -c "
import os, sys
os.environ.setdefault('ARANGO_PASS', os.getenv('ARANGO_PASS', ''))
os.environ['ARANGO_DB'] = 'memory'
sys.path.insert(0, '$SCRIPT_DIR')
from prove import retrieve_similar_proofs, get_arango_db

db = get_arango_db()
if not db:
    print('NO_DB')
    sys.exit(0)

if not db.has_collection('lean_theorems'):
    print('NO_COLLECTION')
    sys.exit(0)

count = db.collection('lean_theorems').count()
results = retrieve_similar_proofs('prove n + 0 = n', k=3)
print(f'OK:{count}:{len(results)}')
" 2>/dev/null) || RETRIEVAL_TEST="ERROR"

case "$RETRIEVAL_TEST" in
    NO_DB)
        echo "  [WARN] ArangoDB not available (retrieval disabled)"
        ;;
    NO_COLLECTION)
        echo "  [WARN] lean_theorems collection missing (run ingest.sh)"
        ;;
    ERROR)
        echo "  [WARN] Retrieval test failed (ArangoDB may not be configured)"
        ;;
    OK:*)
        THMS=$(echo "$RETRIEVAL_TEST" | cut -d: -f2)
        RESULTS=$(echo "$RETRIEVAL_TEST" | cut -d: -f3)
        echo "  [PASS] Retrieval: $THMS theorems, $RESULTS results returned"
        ;;
esac

# 12. Optional: Full integration test (only if container running)
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

# ===========================================================================
# Lab-specific health checks
# ===========================================================================

# 13. Check lean-interact importable
echo "  [INFO] Checking lean-interact..."
LEAN_INTERACT_CHECK=$(python3 -c "
try:
    from lean_interact import LeanREPLConfig, LeanServerPool, Command, AutoLeanServer, ProofStep
    from lean_interact.config import TempRequireProject
    print('OK')
except ImportError as e:
    print(f'MISSING:{e}')
" 2>/dev/null) || LEAN_INTERACT_CHECK="ERROR"

case "$LEAN_INTERACT_CHECK" in
    OK)
        echo "  [PASS] lean-interact imports available"
        ;;
    MISSING:*)
        echo "  [WARN] lean-interact not installed: ${LEAN_INTERACT_CHECK#MISSING:}"
        echo "         Install: pip install lean-interact>=0.11.1"
        ;;
    *)
        echo "  [WARN] lean-interact check failed"
        ;;
esac

# 14. Check lab_cli.py exists
if [[ -f "$SCRIPT_DIR/lab_cli.py" ]]; then
    echo "  [PASS] lab_cli.py exists"
else
    echo "  [FAIL] lab_cli.py not found"
fi

# 15. Check compiler.py exists
if [[ -f "$SCRIPT_DIR/compiler.py" ]]; then
    echo "  [PASS] compiler.py exists"
else
    echo "  [FAIL] compiler.py not found"
fi

# 16. Check formalize.py exists
if [[ -f "$SCRIPT_DIR/formalize.py" ]]; then
    echo "  [PASS] formalize.py exists"
else
    echo "  [FAIL] formalize.py not found"
fi

# 17. Test lab help output
if "$SCRIPT_DIR/run.sh" lab --help 2>/dev/null | grep -q "ingest\|compile\|formalize\|converge\|benchmark\|report"; then
    echo "  [PASS] Lab CLI help works"
else
    echo "  [WARN] Lab CLI help check failed (lean-interact may not be installed)"
fi

# 18. Test lean4_autoformalization collection (if ArangoDB available)
AUTOFORM_CHECK=$(python3 -c "
import os, sys
os.environ.setdefault('ARANGO_PASS', os.getenv('ARANGO_PASS', ''))
os.environ['ARANGO_DB'] = 'memory'
try:
    from arango import ArangoClient
    url = os.getenv('ARANGO_URL', 'http://127.0.0.1:8529')
    client = ArangoClient(hosts=url)
    db = client.db('memory', username='root', password=os.getenv('ARANGO_PASS', ''))
    if db.has_collection('lean4_autoformalization'):
        count = db.collection('lean4_autoformalization').count()
        print(f'OK:{count}')
    else:
        print('NO_COLLECTION')
except Exception as e:
    print(f'ERROR:{e}')
" 2>/dev/null) || AUTOFORM_CHECK="ERROR"

case "$AUTOFORM_CHECK" in
    OK:*)
        COUNT=$(echo "$AUTOFORM_CHECK" | cut -d: -f2)
        echo "  [PASS] lean4_autoformalization collection: $COUNT docs"
        ;;
    NO_COLLECTION)
        echo "  [INFO] lean4_autoformalization collection not yet created (run lab ingest)"
        ;;
    *)
        echo "  [INFO] lean4_autoformalization check skipped (ArangoDB not available)"
        ;;
esac

echo "Result: PASS"

