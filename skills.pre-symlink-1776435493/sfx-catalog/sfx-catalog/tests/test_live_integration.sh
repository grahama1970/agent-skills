#!/usr/bin/env bash
# Live integration test for SFX catalog system
# Tests real-world functionality with actual SFX files and ArangoDB

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Colors for output
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m" # No Color

# Test configuration
SFX_DIR="/mnt/storage12tb/media/sfx"
MANIFEST_FILE="data/sfx_manifest.json"
EXPECTED_FILE_COUNT=166
PERF_THRESHOLD_MS=500

echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     SFX Catalog Live Integration Test               ║${NC}"
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo ""

PASSED=0
FAILED=0
TOTAL=0

# Helper functions
pass_test() {
    PASSED=$((PASSED + 1))
    TOTAL=$((TOTAL + 1))
    echo -e "  ${GREEN}✓ PASS${NC} $1"
}

fail_test() {
    FAILED=$((FAILED + 1))
    TOTAL=$((TOTAL + 1))
    echo -e "  ${RED}✗ FAIL${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# ============================================================================
# Test 1: Check Prerequisites
# ============================================================================
echo -e "${YELLOW}[TEST 1/8]${NC} Checking prerequisites..."

# Check if SFX directory exists
if [ -d "$SFX_DIR" ]; then
    pass_test "SFX directory exists: $SFX_DIR"
else
    fail_test "SFX directory not found: $SFX_DIR"
    echo "  Skipping tests that require real files"
    SFX_DIR="/tmp/sfx_test_empty"
    mkdir -p "$SFX_DIR"
fi

# Check ArangoDB connection
if ./run.sh status 2>&1 | grep -q "Status"; then
    pass_test "CLI is operational"
else
    fail_test "CLI status check failed"
fi

# Count actual MP3 files
if [ -d "$SFX_DIR" ] && [ "$SFX_DIR" != "/tmp/sfx_test_empty" ]; then
    ACTUAL_COUNT=$(find "$SFX_DIR" -type f -name "*.mp3" | wc -l)
    info "Found $ACTUAL_COUNT MP3 files in $SFX_DIR"
    
    if [ "$ACTUAL_COUNT" -ge "$EXPECTED_FILE_COUNT" ]; then
        pass_test "Found expected number of files ($ACTUAL_COUNT >= $EXPECTED_FILE_COUNT)"
    else
        fail_test "File count mismatch (found $ACTUAL_COUNT, expected >= $EXPECTED_FILE_COUNT)"
    fi
fi

echo ""

# ============================================================================
# Test 2: Live Catalog Command
# ============================================================================
echo -e "${YELLOW}[TEST 2/8]${NC} Running live catalog command..."

START_TIME=$(date +%s%N)
if ./run.sh catalog "$SFX_DIR" --output "$MANIFEST_FILE" 2>&1; then
    END_TIME=$(date +%s%N)
    ELAPSED_MS=$(( (END_TIME - START_TIME) / 1000000 ))
    pass_test "Catalog command completed in ${ELAPSED_MS}ms"
else
    fail_test "Catalog command failed"
fi

# Verify manifest file was created
if [ -f "$MANIFEST_FILE" ]; then
    pass_test "Manifest file created: $MANIFEST_FILE"
    
    # Check manifest structure
    if python3 -c "import json; data = json.load(open('$MANIFEST_FILE')); assert 'items' in data; assert 'count' in data" 2>/dev/null; then
        pass_test "Manifest has valid structure (items, count)"
        
        MANIFEST_COUNT=$(python3 -c "import json; print(json.load(open('$MANIFEST_FILE'))['count'])")
        info "Manifest contains $MANIFEST_COUNT items"
        
        if [ "$MANIFEST_COUNT" -gt 0 ]; then
            pass_test "Manifest contains items"
        else
            fail_test "Manifest is empty"
        fi
    else
        fail_test "Manifest structure is invalid"
    fi
else
    fail_test "Manifest file not created"
fi

echo ""

# ============================================================================
# Test 3: Verify Audio Analysis
# ============================================================================
echo -e "${YELLOW}[TEST 3/8]${NC} Verifying audio analysis output..."

if [ -f "$MANIFEST_FILE" ]; then
    # Check if first item has required fields
    FIRST_ITEM=$(python3 << 'EOF'
import json
data = json.load(open("data/sfx_manifest.json"))
if data["items"]:
    item = data["items"][0]
    required_fields = ["duration", "frequency_profile", "envelope", "loudness", "categories", "description"]
    for field in required_fields:
        if field not in item:
            print(f"Missing field: {field}")
            exit(1)
    print("All fields present")
else:
    print("No items")
    exit(1)
EOF
)
    
    if echo "$FIRST_ITEM" | grep -q "All fields present"; then
        pass_test "Audio analysis extracted required metadata"
    else
        fail_test "Missing required metadata fields"
        echo "  $FIRST_ITEM"
    fi
else
    fail_test "Cannot verify - manifest not found"
fi

echo ""

# ============================================================================
# Test 4: Live Ingest Command
# ============================================================================
echo -e "${YELLOW}[TEST 4/8]${NC} Running live ingest to ArangoDB..."

if [ -f "$MANIFEST_FILE" ]; then
    if ./run.sh ingest "$MANIFEST_FILE" 2>&1; then
        pass_test "Ingest command completed successfully"
    else
        fail_test "Ingest command failed"
    fi
    
    # Verify collection was created via /memory count
    python3 << 'EOF'
import sys, json, subprocess
from pathlib import Path

MEMORY_RUN = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "memory" / "run.sh")
try:
    result = subprocess.run(
        [MEMORY_RUN, "count", "--collection", "sfx_library"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"Memory unavailable: {result.stderr}")
        sys.exit(1)
    data = json.loads(result.stdout)
    count = data.get("count", 0)
    if count > 0:
        print(f"Collection 'sfx_library' exists with {count} documents")
        sys.exit(0)
    else:
        print("Collection 'sfx_library' has 0 documents")
        sys.exit(1)
except Exception as e:
    print(f"ArangoDB check failed: {e}")
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        pass_test "ArangoDB collection populated with documents"
    else
        fail_test "ArangoDB collection verification failed"
    fi
else
    fail_test "Cannot ingest - manifest not found"
fi

echo ""

# ============================================================================
# Test 5: Live Search Tests
# ============================================================================
echo -e "${YELLOW}[TEST 5/8]${NC} Running live search queries..."

# Search test 1: Impact sounds
info "Search query: 'impact'"
IMPACT_RESULTS=$(./run.sh search "impact" --limit 5 2>&1)
if echo "$IMPACT_RESULTS" | grep -q "Found"; then
    pass_test "Search for 'impact' returned results"
else
    fail_test "Search for 'impact' returned no results"
fi

# Search test 2: Ambient sounds
info "Search query: 'ambient'"
AMBIENT_RESULTS=$(./run.sh search "ambient" --limit 5 2>&1)
if echo "$AMBIENT_RESULTS" | grep -q "Found\|No results"; then
    pass_test "Search for 'ambient' completed gracefully"
else
    fail_test "Search for 'ambient' failed"
fi

# Search test 3: Transition sounds
info "Search query: 'transition'"
TRANSITION_RESULTS=$(./run.sh search "transition" --limit 5 2>&1)
if echo "$TRANSITION_RESULTS" | grep -q "Found\|No results"; then
    pass_test "Search for 'transition' completed gracefully"
else
    fail_test "Search for 'transition' failed"
fi

# Verify results contain real file paths
if echo "$IMPACT_RESULTS" | grep -qE "\.mp3|pro_studio"; then
    pass_test "Search results include real file references"
else
    fail_test "Search results missing file references"
fi

echo ""

# ============================================================================
# Test 6: Python API Test
# ============================================================================
echo -e "${YELLOW}[TEST 6/8]${NC} Testing Python API from external context..."

# Create temporary test directory
TEST_DIR=$(mktemp -d)
cat > "$TEST_DIR/test_api.py" << 'EOF'
import sys
sys.path.insert(0, '/home/graham/workspace/experiments/pi-mono/.pi/skills/sfx-catalog/src')

# Use absolute imports system.path already includes src/
import sys
import os
sys.path.insert(0, '/home/graham/workspace/experiments/pi-mono/.pi/skills/sfx-catalog')
from src.query_engine import SFXQueryEngine

# Test 1: Import and instantiate
engine = SFXQueryEngine(scope="horus_lore")
print("✓ SFXQueryEngine imported and instantiated")

# Test 2: Perform search
results = engine.search("impact", k=3)
print(f"✓ Search returned {len(results)} results")

# Test 3: Check result structure
if results:
    first = results[0]
    if "filepath" in first or "filename" in first:
        print("✓ Results contain file path information")
    else:
        print("✗ Results missing file path")
        sys.exit(1)
else:
    print("✓ Graceful handling when no results found")

# Test 4: Multiple queries
queries = ["ambient", "transition", "foley"]
for q in queries:
    r = engine.search(q, k=1)
    print(f"  Query '{q}': {len(r)} results")

print("✓ All Python API tests passed")
EOF

if python3 "$TEST_DIR/test_api.py" 2>&1; then
    pass_test "Python API accessible from external context"
    pass_test "Query engine returns usable results"
else
    fail_test "Python API test failed"
fi

rm -rf "$TEST_DIR"

echo ""

# ============================================================================
# Test 7: Performance Verification
# ============================================================================
echo -e "${YELLOW}[TEST 7/8]${NC} Measuring search performance..."

# Run 10 queries and measure timing
info "Running 10 search queries to measure latency..."

TOTAL_MS=0
QUERY_COUNT=10
QUERIES=("impact" "ambient" "transition" "texture" "foley" "low" "high" "quick" "sustained" "sharp")

for query in "${QUERIES[@]}"; do
    START=$(date +%s%N)
    ./run.sh search "$query" --limit 3 >/dev/null 2>&1
    END=$(date +%s%N)
    ELAPSED=$(( (END - START) / 1000000 ))
    TOTAL_MS=$((TOTAL_MS + ELAPSED))
    echo "  Query '$query': ${ELAPSED}ms"
done

AVG_MS=$((TOTAL_MS / QUERY_COUNT))
info "Average query time: ${AVG_MS}ms"

if [ "$AVG_MS" -lt "$PERF_THRESHOLD_MS" ]; then
    pass_test "Average query time ($AVG_MS ms) < threshold ($PERF_THRESHOLD_MS ms)"
else
    fail_test "Average query time ($AVG_MS ms) exceeds threshold ($PERF_THRESHOLD_MS ms)"
fi

echo ""

# ============================================================================
# Test 8: Graceful Degradation
# ============================================================================
echo -e "${YELLOW}[TEST 8/8]${NC} Testing graceful degradation..."

# Test API when ArangoDB is unavailable
cat > /tmp/test_degradation.py << 'EOF'
import sys
sys.path.insert(0, '/home/graham/workspace/experiments/pi-mono/.pi/skills/sfx-catalog')

# Mock unavailable database
from src import memory_bridge
original_init = memory_bridge.SFXMemoryBridge.__init__

def mock_init(self):
    self.available = False
    self.db = None
    self.collection = None

memory_bridge.SFXMemoryBridge.__init__ = mock_init

from src.query_engine import SFXQueryEngine

try:
    engine = SFXQueryEngine()
    results = engine.search("test")
    # Should return empty list, not crash
    print("✓ Graceful degradation works")
    sys.exit(0)
except Exception as e:
    print(f"✗ Exception during degradation: {e}")
    sys.exit(1)
EOF

if python3 /tmp/test_degradation.py 2>&1; then
    pass_test "System degrades gracefully when ArangoDB unavailable"
else
    fail_test "System crashes when ArangoDB unavailable"
fi

rm /tmp/test_degradation.py

echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  Test Summary                        ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Total Tests: $TOTAL"
echo -e "  ${GREEN}Passed: $PASSED${NC}"
echo -e "  ${RED}Failed: $FAILED${NC}"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    echo ""
    echo "Live integration verified:"
    echo "  • Real MP3 files processed with audio analysis"
    echo "  • Manifest created with metadata and categories"
    echo "  • ArangoDB populated with searchable documents"
    echo "  • Search queries return real file paths"
    echo "  • Python API usable from external context"
    echo "  • Performance meets <500ms threshold"
    echo "  • System degrades gracefully"
    echo ""
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    exit 1
fi
