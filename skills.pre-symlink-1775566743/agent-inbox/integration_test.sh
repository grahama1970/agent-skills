#!/usr/bin/env bash
# Integration test for agent-inbox headless dispatch
# Tests the full flow: send → task-monitor → dispatch → verify → ack

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Don't exit on error - we handle failures explicitly
set +e

echo "=========================================="
echo "  Agent-Inbox Integration Test"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}PASS${NC}: $1"; }
fail() { echo -e "${RED}FAIL${NC}: $1"; exit 1; }
info() { echo -e "${YELLOW}INFO${NC}: $1"; }

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Cleanup function
cleanup() {
    info "Cleaning up test messages..."
    rm -f ~/.agent-inbox/pending/integration-test_*.json
    rm -f ~/.agent-inbox/done/integration-test_*.json
    rm -f ~/.agent-inbox/task_states/bug-fix-integration-test_*.json
}

# Run cleanup on exit
trap cleanup EXIT

# ==========================================
# Test 1: Project registration
# ==========================================
echo ""
echo "[1/7] Testing project registration..."

python3 inbox.py register integration-test "$SCRIPT_DIR"
if python3 inbox.py projects | grep -q "integration-test"; then
    pass "Project registration works"
    ((TESTS_PASSED++))
else
    fail "Project registration failed"
    ((TESTS_FAILED++))
fi

# ==========================================
# Test 2: Send message with model
# ==========================================
echo ""
echo "[2/7] Testing send with model specification..."

MSG_ID=$(python3 inbox.py send --to integration-test --type bug --model opus-4.5 \
    "Integration test bug" 2>&1 | grep "Message sent:" | awk '{print $3}')

if [ -n "$MSG_ID" ] && [ -f ~/.agent-inbox/pending/${MSG_ID}.json ]; then
    pass "Message sent with model: $MSG_ID"
    ((TESTS_PASSED++))
else
    fail "Send with model failed"
    ((TESTS_FAILED++))
fi

# ==========================================
# Test 3: Verify dispatch config in message
# ==========================================
echo ""
echo "[3/7] Testing dispatch config in message..."

if cat ~/.agent-inbox/pending/${MSG_ID}.json | grep -q '"model": "opus-4.5"'; then
    pass "Dispatch config includes model"
    ((TESTS_PASSED++))
else
    fail "Dispatch config missing model"
    ((TESTS_FAILED++))
fi

# ==========================================
# Test 4: Task-monitor state file created
# ==========================================
echo ""
echo "[4/7] Testing task-monitor integration..."

if [ -f ~/.agent-inbox/task_states/bug-fix-${MSG_ID}.json ]; then
    pass "Task-monitor state file created"
    ((TESTS_PASSED++))
else
    fail "Task-monitor state file not created"
    ((TESTS_FAILED++))
fi

# ==========================================
# Test 5: Status update
# ==========================================
echo ""
echo "[5/7] Testing status update..."

python3 inbox.py update-status "$MSG_ID" in_progress --note "Testing"

if cat ~/.agent-inbox/pending/${MSG_ID}.json | grep -q '"status": "in_progress"'; then
    pass "Status updated to in_progress"
    ((TESTS_PASSED++))
else
    fail "Status update failed"
    ((TESTS_FAILED++))
fi

# ==========================================
# Test 6: Thread reply
# ==========================================
echo ""
echo "[6/7] Testing thread reply..."

REPLY_OUTPUT=$(python3 inbox.py reply "$MSG_ID" "Reply to test message" 2>&1)

if echo "$REPLY_OUTPUT" | grep -q "Thread: $MSG_ID"; then
    pass "Reply correctly threads to parent"
    ((TESTS_PASSED++))
else
    fail "Thread reply failed"
    ((TESTS_FAILED++))
fi

# ==========================================
# Test 7: List thread
# ==========================================
echo ""
echo "[7/7] Testing thread listing..."

THREAD_OUTPUT=$(python3 inbox.py thread "$MSG_ID" 2>&1)

if echo "$THREAD_OUTPUT" | grep -q "2 messages"; then
    pass "Thread listing shows both messages"
    ((TESTS_PASSED++))
else
    fail "Thread listing incorrect"
    ((TESTS_FAILED++))
fi

# ==========================================
# Summary
# ==========================================
echo ""
echo "=========================================="
echo "  SUMMARY"
echo "=========================================="
echo -e "  Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "  Failed: ${RED}${TESTS_FAILED}${NC}"
echo "=========================================="

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All integration tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
