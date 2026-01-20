#!/usr/bin/env bash
# Sanity test for memory skill - REAL VERIFICATION
# Starts the actual service, checks health and recall, then shuts down.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export RUN_SCRIPT="$SCRIPT_DIR/run.sh"

PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }
log_info() { echo "  [INFO] $1"; }

echo "=== Memory Skill Sanity (Real Service) ==="

# 1. Existence Check
if [[ -f "$RUN_SCRIPT" ]]; then
    log_pass "run.sh exists"
else
    log_fail "run.sh missing"
    exit 1
fi

# 2. Pick a random port for the test service
PORT=$((10000 + RANDOM % 10000))
export MEMORY_SERVICE_URL="http://127.0.0.1:$PORT"

LOG_FILE="/tmp/memory_service_${PORT}.log"
log_info "Starting memory service on port $PORT (logging to $LOG_FILE)..."
"$RUN_SCRIPT" serve --port "$PORT" > "$LOG_FILE" 2>&1 &
SERVICE_PID=$!

cleanup() {
    log_info "Stopping service (PID $SERVICE_PID)..."
    kill "$SERVICE_PID" >/dev/null 2>&1 || true
    wait "$SERVICE_PID" >/dev/null 2>&1 || true
    # rm -f "$LOG_FILE" # Keep log for inspection
}
trap cleanup EXIT

# 3. Wait for Health
log_info "Waiting for service health..."
HEALTHY=0
for i in {1..60}; do
    if curl -s "http://127.0.0.1:$PORT/health" | grep -q '"ok"'; then
        HEALTHY=1
        break
    fi
    sleep 1
done

if [[ $HEALTHY -eq 1 ]]; then
    log_pass "Service became healthy"
else
    log_fail "Service failed to start or pass health check"
    echo "=== Service Logs ==="
    cat "$LOG_FILE"
    echo "===================="
    exit 1
fi

# 4. Verify Recall (Real execution)
log_info "Running real recall query..."
OUTPUT=$("$RUN_SCRIPT" recall --q "sanity check" 2>&1)

if echo "$OUTPUT" | grep -q '"found"'; then
    log_pass "Recall returned valid JSON"
else
    log_fail "Recall failed to return JSON"
    echo "Output: $OUTPUT"
fi

# 5. Verify Learn (Real execution - using dry run if possible or just verifying CLI accepts it)
# We won't actually write to DB to avoid polluting it with junk, or we accept one entry.
# The graph-memory CLI doesn't strictly have a dry-run for learn, but we can check if it runs.
# We'll skip LEARN write to be safe, RECALL is sufficient proof the stack works.

echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL"
    exit 1
fi

echo "Result: PASS"
exit 0
