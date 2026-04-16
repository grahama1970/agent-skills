#!/bin/bash
# sanity.sh - Verify icon-creator skill functionality
#
# Exit 0 on success, non-zero on failure

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="/tmp/icon-creator-test-$$"
PASS=0
FAIL=0

cleanup() {
    rm -rf "$TEST_DIR" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Icon Creator Sanity Test ==="
echo ""

# Test 1: Check dependencies
echo -n "1. Checking dependencies... "
if which identify convert curl >/dev/null 2>&1; then
    echo "✓ PASS"
    ((PASS++))
else
    echo "✗ FAIL - Missing: identify, convert, or curl"
    ((FAIL++))
fi

# Test 2: Fetch icon from Lucide CDN
echo -n "2. Fetching 'folder' icon from Lucide... "
mkdir -p "$TEST_DIR"
if python3 "$SKILL_DIR/creator.py" fetch folder --name test_folder --dir "$TEST_DIR" >/dev/null 2>&1; then
    echo "✓ PASS"
    ((PASS++))
else
    echo "✗ FAIL - Could not fetch icon"
    ((FAIL++))
fi

# Test 3: Verify output files exist
echo -n "3. Verifying output files exist... "
if [ -f "$TEST_DIR/test_folder_white.png" ] && [ -f "$TEST_DIR/test_folder_active.png" ]; then
    echo "✓ PASS"
    ((PASS++))
else
    echo "✗ FAIL - Output files missing"
    ((FAIL++))
fi

# Test 4: Verify dimensions are 72x72
echo -n "4. Verifying dimensions (72x72)... "
WHITE_SIZE=$(identify -format "%wx%h" "$TEST_DIR/test_folder_white.png" 2>/dev/null || echo "error")
ACTIVE_SIZE=$(identify -format "%wx%h" "$TEST_DIR/test_folder_active.png" 2>/dev/null || echo "error")
if [ "$WHITE_SIZE" = "72x72" ] && [ "$ACTIVE_SIZE" = "72x72" ]; then
    echo "✓ PASS (white: $WHITE_SIZE, active: $ACTIVE_SIZE)"
    ((PASS++))
else
    echo "✗ FAIL - Got white=$WHITE_SIZE, active=$ACTIVE_SIZE (expected 72x72)"
    ((FAIL++))
fi

# Test 5: Test --active-color flag
echo -n "5. Testing --active-color flag... "
if python3 "$SKILL_DIR/creator.py" fetch play --name test_play --dir "$TEST_DIR" --active-color "#FF6600" >/dev/null 2>&1; then
    if [ -f "$TEST_DIR/test_play_active.png" ]; then
        echo "✓ PASS"
        ((PASS++))
    else
        echo "✗ FAIL - Active file not created"
        ((FAIL++))
    fi
else
    echo "✗ FAIL - Command failed"
    ((FAIL++))
fi

# Test 6: Test list command
echo -n "6. Testing list command... "
if python3 "$SKILL_DIR/creator.py" list 2>&1 | grep -q "folder"; then
    echo "✓ PASS"
    ((PASS++))
else
    echo "✗ FAIL - List command failed"
    ((FAIL++))
fi

# Test 7: run.sh --help
echo -n "7. Testing run.sh --help... "
if "$SKILL_DIR/run.sh" --help 2>&1 | grep -q "Icon Creator"; then
    echo "✓ PASS"
    ((PASS++))
else
    echo "✗ FAIL - Help text missing"
    ((FAIL++))
fi

# Summary
echo ""
echo "=== Results ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "✓ All sanity checks passed!"
    exit 0
else
    echo "✗ Some checks failed"
    exit 1
fi
