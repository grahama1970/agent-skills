#!/usr/bin/env bash
# Sanity test for memory skill CLI wrapper

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0

log_pass() { echo "  [PASS] $1"; ((++PASS)); }
log_fail() { echo "  [FAIL] $1"; ((++FAIL)); }

echo "=== memory Skill Sanity Tests ==="
echo ""

echo "1. run.sh exists"
if [[ -f "$SCRIPT_DIR/run.sh" ]]; then
    log_pass "run.sh present"
else
    log_fail "run.sh missing"
fi

echo "2. Help command"
OUTPUT=$("$SCRIPT_DIR/run.sh" --help 2>&1 || true)
if echo "$OUTPUT" | grep -q "Memory Agent CLI"; then
    log_pass "Help text renders"
else
    log_fail "Help text missing"
fi

# -----------------------------------------------------------------------------
# 3. Fast path recall/learn via stub server
# -----------------------------------------------------------------------------
echo "3. HTTP fast path"

PORT_FILE=$(mktemp)
python - <<'PY' "$PORT_FILE" &
import json, http.server, socketserver, sys, pathlib
port_file = pathlib.Path(sys.argv[1])

class Handler(http.server.BaseHTTPRequestHandler):
    def _write(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, *args, **kwargs):
        return

    def do_GET(self):
        if self.path == "/health":
            self._write(200, {"status": "ok", "model": "stub"})
        else:
            self._write(404, {"error": "not-found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/recall":
            self._write(200, {"found": False, "items": [], "echo": data})
        elif self.path == "/learn":
            self._write(200, {"ok": True, "stored": data})
        else:
            self._write(404, {"error": "not-found"})

with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
    port_file.write_text(str(httpd.server_address[1]))
    httpd.serve_forever()
PY
SERVER_PID=$!

cleanup() {
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    rm -f "$PORT_FILE"
}
trap cleanup EXIT

PORT=""
for _ in {1..50}; do
    if [[ -s "$PORT_FILE" ]]; then
        PORT=$(cat "$PORT_FILE")
        break
    fi
    sleep 0.1
done

if [[ -z "$PORT" ]]; then
    log_fail "stub server failed to start"
else
    export MEMORY_SERVICE_URL="http://127.0.0.1:$PORT"

    RECALL_OUTPUT=$("$SCRIPT_DIR/run.sh" recall --q "smoke sanity test" 2>&1 || true)
    if echo "$RECALL_OUTPUT" | grep -q '"found"'; then
        log_pass "recall hits stub service"
    else
        log_fail "recall did not return JSON"
    fi

    LEARN_OUTPUT=$("$SCRIPT_DIR/run.sh" learn --problem "Smoke" --solution "Works" --scope sanity 2>&1 || true)
    if echo "$LEARN_OUTPUT" | grep -q '"ok"'; then
        log_pass "learn hits stub service"
    else
        log_fail "learn did not return JSON"
    fi

    HEALTH_OUTPUT=$("$SCRIPT_DIR/run.sh" health 2>&1 || true)
    if echo "$HEALTH_OUTPUT" | grep -q '"status"'; then
        log_pass "health endpoint reachable"
    else
        log_fail "health endpoint unreachable"
    fi
fi

echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo "Result: FAIL"
    exit 1
fi

echo "Result: PASS"
exit 0
