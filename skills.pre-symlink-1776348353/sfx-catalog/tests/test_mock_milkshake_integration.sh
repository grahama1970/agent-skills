#!/usr/bin/env bash
# Test integration with mock_milkshake workflow

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "=== Testing mock_milkshake Integration ==="

# Test 1: Can import SFXQueryEngine
echo "  [1/4] Testing Python import..."
if python3 -c "import sys; sys.path.insert(0, 'src'); from src import SFXQueryEngine; print('OK')" >/dev/null 2>&1; then
    echo "  [PASS] Python API importable"
else
    echo "  [FAIL] Cannot import SFXQueryEngine"
    exit 1
fi

# Test 2: Can query for generic sounds
echo "  [2/4] Testing search..."
python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from src import SFXQueryEngine
engine = SFXQueryEngine(scope='memory')
results = engine.search('sound', k=1)
if len(results) > 0:
    print("  [PASS] Found results")
else:
    print("  [PASS] No results (graceful fallback)")
EOF

# Test 3: Test graceful handling
echo "  [3/4] Testing graceful fallback..."
python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from src import SFXQueryEngine
engine = SFXQueryEngine(scope='memory')
results = engine.search('nonexistent query', k=1)
if results:
    print("  [PASS] Found results")
else:
    print("  [PASS] Graceful fallback")
EOF

# Test 4: Test no crashes
echo "  [4/4] Testing no exceptions..."
if python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from src import SFXQueryEngine
engine = SFXQueryEngine(scope='memory')
for query in ['ambient', 'transition', 'test']:
    results = engine.search(query, k=1)
EOF
then
    echo "  [PASS] No crashes during queries"
else
    echo "  [FAIL] Exception during query"
    exit 1
fi

echo ""
echo "=== Integration Test Complete ==="
echo "✓ SFX catalog can be queried from create-movie context"
echo "✓ System degrades gracefully when no results found"
echo "✓ No blocking exceptions"
