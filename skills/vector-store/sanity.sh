#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SCRIPT="$SCRIPT_DIR/run.sh"
PORT_FILE="$SCRIPT_DIR/.port"
LOG_FILE="/tmp/vector_store_sanity.log"

echo "=== Vector Store Sanity Check ==="

if [[ ! -f "$RUN_SCRIPT" ]]; then
    echo "  [FAIL] run.sh missing"
    exit 1
fi

# Cleanup previous
rm -f "$PORT_FILE"
# Ensure we pick a random-ish port range to avoid conflicts if multiple runs happen?
# run.sh handles port finding, but let's give it a hint if we want, or trust it.
# We'll trust run.sh logic.

echo "  [INFO] Starting service (log: $LOG_FILE)..."
"$RUN_SCRIPT" > "$LOG_FILE" 2>&1 &
SERVICE_PID=$!

cleanup() {
    echo "  [INFO] Stopping service (PID $SERVICE_PID)..."
    kill "$SERVICE_PID" >/dev/null 2>&1 || true
    wait "$SERVICE_PID" >/dev/null 2>&1 || true
    rm -f "$PORT_FILE"
}
trap cleanup EXIT

# Wait for port file
echo "  [INFO] Waiting for startup..."
found_port=0
for i in {1..30}; do
    if [[ -f "$PORT_FILE" ]]; then
        found_port=1
        break
    fi
    sleep 1
done

if [[ $found_port -eq 0 ]]; then
    echo "  [FAIL] Service timed out (no .port file)"
    cat "$LOG_FILE"
    exit 1
fi

PORT=$(cat "$PORT_FILE")
URL="http://127.0.0.1:${PORT}"
echo "  [INFO] Service on port $PORT"

# Wait for health
echo "  [INFO] Checking health..."
healthy=0
for i in {1..30}; do
    if curl -s "${URL}/health" | grep -q "ok"; then
        healthy=1
        break
    fi
    sleep 1
done

if [[ $healthy -eq 0 ]]; then
    echo "  [FAIL] Health check failed"
    cat "$LOG_FILE"
    exit 1
fi

echo "  [PASS] Service healthy"

# Execute logic from original sanity script
echo "  [INFO] Resetting index..."
curl -s -X DELETE "${URL}/reset" > /dev/null

echo "  [INFO] Indexing vectors..."
curl -s -X POST "${URL}/index" \
  -H "Content-Type: application/json" \
  -d '{
    "ids": ["vec1", "vec2", "vec3"],
    "vectors": [[1.0, 0.0], [0.0, 1.0], [0.707, 0.707]]
  }' > /dev/null

echo "  [INFO] Searching..."
RESULT=$(curl -s -X POST "${URL}/search" \
  -H "Content-Type: application/json" \
  -d '{ "query": [1.0, 0.0], "k": 3 }')

if echo "$RESULT" | grep -q "vec1"; then
    echo "  [PASS] Search returned expected results"
else
    echo "  [FAIL] Search failed"
    echo "Result: $RESULT"
    exit 1
fi

echo "Result: PASS"
exit 0
