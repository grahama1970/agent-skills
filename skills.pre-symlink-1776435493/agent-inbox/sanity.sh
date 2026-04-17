#!/usr/bin/env bash
# Sanity tests for agent-inbox skill
# Run: ./sanity.sh
# Exit codes: 0 = all pass, 1 = failures

set -euo pipefail

# Load environment from common .env files
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SKILL_DIR/../common.sh" 2>/dev/null || true
SCRIPT_DIR="$SKILL_DIR"

PASS=0
FAIL=0
MISSING_DEPS=()

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }
log_missing() {
    echo "  [MISS] $1"
    MISSING_DEPS+=("$2")
}

echo "=== Agent Inbox Skill Sanity Tests ==="
echo ""

# Use temp directory for tests
export AGENT_INBOX_DIR=$(mktemp -d)
trap "rm -rf $AGENT_INBOX_DIR" EXIT

INBOX_PY="$SCRIPT_DIR/inbox.py"

# -----------------------------------------------------------------------------
# 1. Script availability
# -----------------------------------------------------------------------------
echo "1. Script availability"

if [[ -f "$INBOX_PY" ]]; then
    log_pass "inbox.py exists"
else
    log_fail "inbox.py not found"
    exit 1
fi

if python3 "$INBOX_PY" --help &>/dev/null; then
    log_pass "inbox.py --help"
else
    log_fail "inbox.py --help"
fi

# -----------------------------------------------------------------------------
# 2. Send command
# -----------------------------------------------------------------------------
echo "2. Send command"

SEND_OUTPUT=$(python3 "$INBOX_PY" send --to testproject --type bug --priority high "Test bug message" 2>&1)
if echo "$SEND_OUTPUT" | grep -q "Message sent"; then
    log_pass "send creates message"
else
    log_fail "send failed"
fi

# Check file was created
if ls "$AGENT_INBOX_DIR/pending/"*.json &>/dev/null; then
    log_pass "message file created in pending/"
else
    log_fail "message file not created"
fi

# -----------------------------------------------------------------------------
# 3. List command
# -----------------------------------------------------------------------------
echo "3. List command"

LIST_OUTPUT=$(python3 "$INBOX_PY" list --project testproject 2>&1)
if echo "$LIST_OUTPUT" | grep -q "testproject"; then
    log_pass "list shows message"
else
    log_fail "list doesn't show message"
fi

LIST_JSON=$(python3 "$INBOX_PY" list --project testproject --json 2>&1)
if echo "$LIST_JSON" | grep -q '"to": "testproject"'; then
    log_pass "list --json works"
else
    log_fail "list --json failed"
fi

# -----------------------------------------------------------------------------
# 4. Read command
# -----------------------------------------------------------------------------
echo "4. Read command"

# Get the message ID from the file
MSG_ID=$(basename "$AGENT_INBOX_DIR/pending/"*.json .json)

READ_OUTPUT=$(python3 "$INBOX_PY" read "$MSG_ID" 2>&1)
if echo "$READ_OUTPUT" | grep -q "Test bug message"; then
    log_pass "read shows message content"
else
    log_fail "read failed"
fi

# -----------------------------------------------------------------------------
# 5. Check command
# -----------------------------------------------------------------------------
echo "5. Check command"

CHECK_OUTPUT=$(python3 "$INBOX_PY" check --project testproject 2>&1 || true)
if echo "$CHECK_OUTPUT" | grep -q "pending message"; then
    log_pass "check reports pending messages"
else
    log_fail "check failed"
fi

CHECK_COUNT=$(python3 "$INBOX_PY" check --project testproject --quiet 2>&1 || true)
if [[ "$CHECK_COUNT" == "1" ]]; then
    log_pass "check --quiet returns count"
else
    log_fail "check --quiet returned '$CHECK_COUNT' instead of '1'"
fi

# -----------------------------------------------------------------------------
# 6. Ack command
# -----------------------------------------------------------------------------
echo "6. Ack command"

ACK_OUTPUT=$(python3 "$INBOX_PY" ack "$MSG_ID" --note "Fixed in test" 2>&1)
if echo "$ACK_OUTPUT" | grep -q "acknowledged"; then
    log_pass "ack acknowledges message"
else
    log_fail "ack failed"
fi

# Check file moved to done
if [[ -f "$AGENT_INBOX_DIR/done/$MSG_ID.json" ]]; then
    log_pass "message moved to done/"
else
    log_fail "message not moved to done/"
fi

# Check pending is now empty
REMAINING=$(python3 "$INBOX_PY" check --quiet 2>&1 || true)
if [[ "$REMAINING" == "0" ]]; then
    log_pass "no pending messages after ack"
else
    log_fail "still have pending messages after ack"
fi

# -----------------------------------------------------------------------------
# 7. Python API
# -----------------------------------------------------------------------------
echo "7. Python API"

API_TEST=$(PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}" AGENT_INBOX_DIR="$AGENT_INBOX_DIR" python3 -c "
from inbox import send, list_messages, check_inbox

# Send a new message
send('apitest', 'API test message', msg_type='info')

# List
msgs = list_messages(project='apitest')
assert len(msgs) == 1
assert msgs[0]['to'] == 'apitest'

# Check
count = check_inbox(project='apitest', quiet=True)
assert count == 1

print('ok')
" 2>&1 || echo "fail")

if echo "$API_TEST" | grep -q "^ok$"; then
    log_pass "Python API works"
else
    echo "    API_TEST output: $API_TEST"
    log_fail "Python API failed"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Missing: ${#MISSING_DEPS[@]}"

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo ""
    echo "=== Missing Dependencies ==="
    echo "Run these commands to install missing components:"
    echo ""
    printf '%s\n' "${MISSING_DEPS[@]}" | sort -u | while read -r cmd; do
        echo "  $cmd"
    done
fi

echo ""
if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL ($FAIL failures)"
    exit 1
elif [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    echo "Result: INCOMPLETE (missing dependencies)"
    exit 0
else
    echo "Result: PASS"
    exit 0
fi
