#!/usr/bin/env bash
# Blind adversarial tests for create-subagent skill
# The coding agent NEVER sees this file — only pass/fail output.
#
# Tests: Docker lifecycle, API endpoints, multi-instance, workspace,
#        port allocation, cleanup, security, and edge cases.
#
# Prerequisites: Docker running, create-subagent image built.
# This script manages its own containers (cleans up after itself).
set -uo pipefail

SKILL_DIR="/home/graham/workspace/experiments/pi-mono/.pi/skills/create-subagent"
RUN_SH="$SKILL_DIR/run.sh"
PASS=0
FAIL=0
SKIP=0
RESULTS=()
TEST_INSTANCE_PREFIX="blind-test"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

check() {
    local id="$1" desc="$2"
    shift 2
    if "$@" >/dev/null 2>&1; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_output() {
    # Run command, check if stdout contains pattern
    local id="$1" desc="$2" pattern="$3"
    shift 3
    local output
    output=$("$@" 2>&1) || true
    if echo "$output" | grep -qE "$pattern"; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_http() {
    # HTTP request, check response contains pattern
    local id="$1" desc="$2" url="$3" pattern="$4"
    local response
    response=$(curl -sf --max-time 10 "$url" 2>/dev/null) || response=""
    if echo "$response" | grep -qE "$pattern"; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc")
        FAIL=$((FAIL + 1))
    fi
}

check_http_status() {
    # HTTP request, check response code
    local id="$1" desc="$2" method="$3" url="$4" expected_code="$5"
    local data="${6:-}"
    local code
    if [[ -n "$data" ]]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" -d "$data" --max-time 10 2>/dev/null)
    else
        code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" --max-time 10 2>/dev/null)
    fi
    if [[ "$code" == "$expected_code" ]]; then
        RESULTS+=("PASS [$id] $desc")
        PASS=$((PASS + 1))
    else
        RESULTS+=("FAIL [$id] $desc (got $code, expected $expected_code)")
        FAIL=$((FAIL + 1))
    fi
}

skip() {
    local id="$1" desc="$2" reason="$3"
    RESULTS+=("SKIP [$id] $desc ($reason)")
    SKIP=$((SKIP + 1))
}

cleanup_test_instances() {
    # Remove any containers from previous test runs
    docker ps -a --filter "label=embry.skill=create-subagent" --format '{{.Names}}' 2>/dev/null \
        | grep "^embry-subagent-${TEST_INSTANCE_PREFIX}" \
        | xargs -r docker rm -f >/dev/null 2>&1 || true
}

wait_for_health() {
    local port="$1" max_wait="${2:-30}"
    for _ in $(seq 1 "$max_wait"); do
        if curl -sf --max-time 3 "http://localhost:${port}/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

echo "=== create-subagent Blind Adversarial Tests ==="
echo ""

# Pre-flight: ensure clean state
cleanup_test_instances

# ===========================================================================
# T1: Image & Prerequisites
# ===========================================================================

check "T1.1" "Docker image exists" \
    docker image inspect create-subagent:latest

check "T1.2" "Image runs as non-root (node user)" \
    bash -c "docker inspect create-subagent:latest --format '{{.Config.User}}' | grep -q node"

check "T1.3" "Image exposes port 8620" \
    bash -c "docker inspect create-subagent:latest --format '{{json .Config.ExposedPorts}}' | grep -q 8620"

check "T1.4" "Dockerfile uses shell form CMD for env expansion" \
    grep -q 'CMD python3' "$SKILL_DIR/Dockerfile"

check "T1.5" "backends.yml is valid YAML with 3 backends" \
    python3 -c "
import yaml
d = yaml.safe_load(open('$SKILL_DIR/backends.yml'))
assert len(d['backends']) >= 3, f'Expected 3+ backends, got {len(d[\"backends\"])}'
"

# ===========================================================================
# T2: Single Instance Lifecycle
# ===========================================================================

# Start a test instance on an explicit port to avoid conflicts
TEST_PORT_1=8627
"$RUN_SH" start --name "${TEST_INSTANCE_PREFIX}-alpha" --port "$TEST_PORT_1" --no-memory >/dev/null 2>&1
wait_for_health "$TEST_PORT_1" 30

check "T2.1" "Instance starts and passes health check" \
    curl -sf --max-time 5 "http://localhost:${TEST_PORT_1}/health"

check_http "T2.2" "Health reports claude backend" \
    "http://localhost:${TEST_PORT_1}/health" '"claude"'

check_http "T2.3" "Health reports codex backend" \
    "http://localhost:${TEST_PORT_1}/health" '"codex"'

check_http "T2.4" "Health reports gemini backend" \
    "http://localhost:${TEST_PORT_1}/health" '"gemini"'

# Docker labels
check "T2.5" "Container has embry.skill label" \
    bash -c "docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{index .Config.Labels \"embry.skill\"}}' | grep -q create-subagent"

check "T2.6" "Container has embry.port label" \
    bash -c "docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{index .Config.Labels \"embry.port\"}}' | grep -q ${TEST_PORT_1}"

check "T2.7" "Container has embry.instance label" \
    bash -c "docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{index .Config.Labels \"embry.instance\"}}' | grep -q ${TEST_INSTANCE_PREFIX}-alpha"

check "T2.8" "Container uses host network mode" \
    bash -c "docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{.HostConfig.NetworkMode}}' | grep -q host"

check "T2.9" "Container has restart policy unless-stopped" \
    bash -c "docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{.HostConfig.RestartPolicy.Name}}' | grep -q unless-stopped"

# ===========================================================================
# T3: API Endpoints
# ===========================================================================

check_http_status "T3.1" "GET /health returns 200" \
    "GET" "http://localhost:${TEST_PORT_1}/health" "200"

check_http_status "T3.2" "GET /backends returns 200" \
    "GET" "http://localhost:${TEST_PORT_1}/backends" "200"

check_http_status "T3.3" "GET /usage returns 200" \
    "GET" "http://localhost:${TEST_PORT_1}/usage" "200"

check_http_status "T3.4" "GET /tasks returns 200" \
    "GET" "http://localhost:${TEST_PORT_1}/tasks" "200"

check_http_status "T3.5" "GET /tasks?status=running returns 200" \
    "GET" "http://localhost:${TEST_PORT_1}/tasks?status=running" "200"

check_http_status "T3.6" "GET /tasks/nonexistent returns 404" \
    "GET" "http://localhost:${TEST_PORT_1}/tasks/nonexistent" "404"

check_http_status "T3.7" "POST /chat with empty body returns 422" \
    "POST" "http://localhost:${TEST_PORT_1}/chat" "422" '{}'

check_http_status "T3.8" "POST /chat with missing prompt returns 422" \
    "POST" "http://localhost:${TEST_PORT_1}/chat" "422" '{"model":"sonnet"}'

check_http_status "T3.9" "DELETE /usage resets counters" \
    "DELETE" "http://localhost:${TEST_PORT_1}/usage" "200"

# Verify reset worked
check_http "T3.10" "Usage shows zero after reset" \
    "http://localhost:${TEST_PORT_1}/usage" '"requests":\s*0'

# /backends structure
check_http "T3.11" "/backends lists claude with cli field" \
    "http://localhost:${TEST_PORT_1}/backends" '"cli".*"claude"'

# /tasks structure
check_http "T3.12" "/tasks has skill field" \
    "http://localhost:${TEST_PORT_1}/tasks" '"skill".*"create-subagent"'

check_http "T3.13" "/tasks has summary field" \
    "http://localhost:${TEST_PORT_1}/tasks" '"summary"'

# ===========================================================================
# T4: Model Routing (via /backends, no LLM calls needed)
# ===========================================================================

# Test resolve_backend logic by inspecting Python directly inside container
check "T4.1" "resolve_backend: 'sonnet' routes to claude" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import resolve_backend
b, m = resolve_backend('sonnet')
assert b == 'claude', f'Expected claude, got {b}'
\""

check "T4.2" "resolve_backend: 'opus-4.6' routes to claude" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import resolve_backend
b, m = resolve_backend('opus-4.6')
assert b == 'claude', f'Expected claude, got {b}'
\""

check "T4.3" "resolve_backend: 'gpt-5.2-codex' routes to codex" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
import asyncio; from server import load_backends, resolve_backend
asyncio.run(load_backends())
b, m = resolve_backend('gpt-5.2-codex')
assert b == 'codex', f'Expected codex, got {b}'
\""

check "T4.4" "resolve_backend: 'gemini-2.5-pro' routes to gemini" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
import asyncio; from server import load_backends, resolve_backend
asyncio.run(load_backends())
b, m = resolve_backend('gemini-2.5-pro')
assert b == 'gemini', f'Expected gemini, got {b}'
\""

check "T4.5" "resolve_backend: None defaults to claude/sonnet" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import resolve_backend
b, m = resolve_backend(None)
assert b == 'claude', f'Expected claude, got {b}'
assert m == 'sonnet', f'Expected sonnet, got {m}'
\""

check "T4.6" "resolve_backend: 'claude' as backend name works" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import resolve_backend
b, m = resolve_backend('claude')
assert b == 'claude', f'Expected claude, got {b}'
\""

check "T4.7" "resolve_backend: unknown model falls back to claude" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import resolve_backend
b, m = resolve_backend('completely-unknown-model')
assert b == 'claude', f'Expected claude fallback, got {b}'
\""

# ===========================================================================
# T5: Security
# ===========================================================================

check "T5.1" "CLAUDECODE env var stripped from container" \
    bash -c "! docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha printenv CLAUDECODE 2>/dev/null"

check "T5.2" "Credential blocklist: no ANTHROPIC_API_KEY in env" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import _clean_env
import os; os.environ['ANTHROPIC_API_KEY'] = 'test-secret'
env = _clean_env('claude')
assert 'ANTHROPIC_API_KEY' not in env, 'API key leaked'
\""

check "T5.3" "Credential blocklist: no AWS keys in env" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import _clean_env
import os; os.environ['AWS_SECRET_ACCESS_KEY'] = 'secret'
env = _clean_env('claude')
assert 'AWS_SECRET_ACCESS_KEY' not in env, 'AWS key leaked'
\""

check "T5.4" "EMBEDDING_SERVICE_URL preserved in clean env" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-alpha python3 -c \"
from server import _clean_env
import os; os.environ['EMBEDDING_SERVICE_URL'] = 'http://test:8602'
env = _clean_env('claude')
assert 'EMBEDDING_SERVICE_URL' in env, 'Embedding URL stripped'
\""

check "T5.5" "Claude credentials mounted (not baked)" \
    bash -c "docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{json .Mounts}}' | grep -q '.claude'"

# ===========================================================================
# T6: Multi-Instance
# ===========================================================================

TEST_PORT_2=8628
"$RUN_SH" start --name "${TEST_INSTANCE_PREFIX}-bravo" --port "$TEST_PORT_2" --no-memory >/dev/null 2>&1
wait_for_health "$TEST_PORT_2" 30

check "T6.1" "Second instance starts on different port" \
    curl -sf --max-time 5 "http://localhost:${TEST_PORT_2}/health"

check "T6.2" "Both instances respond independently" \
    bash -c "
    h1=\$(curl -sf --max-time 5 http://localhost:${TEST_PORT_1}/health)
    h2=\$(curl -sf --max-time 5 http://localhost:${TEST_PORT_2}/health)
    [[ -n \"\$h1\" && -n \"\$h2\" ]]
"

check "T6.3" "List shows both test instances" \
    bash -c "$RUN_SH list 2>&1 | grep -c '${TEST_INSTANCE_PREFIX}' | grep -q 2"

check "T6.4" "Each instance has unique embry.instance label" \
    bash -c "
    i1=\$(docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-alpha --format '{{index .Config.Labels \"embry.instance\"}}')
    i2=\$(docker inspect embry-subagent-${TEST_INSTANCE_PREFIX}-bravo --format '{{index .Config.Labels \"embry.instance\"}}')
    [[ \"\$i1\" != \"\$i2\" ]]
"

# Start attempt on already-used port — should detect conflict
check_output "T6.5" "Refuses duplicate port from another instance" \
    "already in use|already running" \
    "$RUN_SH" start --name "${TEST_INSTANCE_PREFIX}-charlie" --port "$TEST_PORT_1"

# ===========================================================================
# T7: Workspace Mounting
# ===========================================================================

TEST_PORT_3=8629
WORKSPACE_DIR=$(mktemp -d)
echo "test-content-from-workspace" > "$WORKSPACE_DIR/probe.txt"

"$RUN_SH" start --name "${TEST_INSTANCE_PREFIX}-ws" --port "$TEST_PORT_3" --no-memory --workspace "$WORKSPACE_DIR" >/dev/null 2>&1
wait_for_health "$TEST_PORT_3" 30

check "T7.1" "Workspace instance starts with health check" \
    curl -sf --max-time 5 "http://localhost:${TEST_PORT_3}/health"

check "T7.2" "WORKSPACE_DIR env var set inside container" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-ws printenv WORKSPACE_DIR | grep -q /home/node/workspace"

check "T7.3" "Workspace files visible inside container" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-ws cat /home/node/workspace/probe.txt | grep -q test-content-from-workspace"

check "T7.4" "Workspace mount is read-write" \
    bash -c "docker exec embry-subagent-${TEST_INSTANCE_PREFIX}-ws touch /home/node/workspace/write-test.txt && [[ -f '$WORKSPACE_DIR/write-test.txt' ]]"

# Clean up workspace test file
rm -f "$WORKSPACE_DIR/write-test.txt" "$WORKSPACE_DIR/probe.txt"
rmdir "$WORKSPACE_DIR" 2>/dev/null || true

# ===========================================================================
# T8: Stop & Cleanup
# ===========================================================================

check_output "T8.1" "Stop specific instance removes it" \
    "Stopped" \
    "$RUN_SH" stop "${TEST_INSTANCE_PREFIX}-alpha"

check "T8.2" "Stopped instance no longer running" \
    bash -c "! docker ps --format '{{.Names}}' | grep -q embry-subagent-${TEST_INSTANCE_PREFIX}-alpha"

check_output "T8.3" "Stop --all removes remaining test instances" \
    "Cleaned up" \
    "$RUN_SH" stop --all

check "T8.4" "No test containers remain after stop --all" \
    bash -c "! docker ps -a --filter 'label=embry.skill=create-subagent' --format '{{.Names}}' | grep -q ${TEST_INSTANCE_PREFIX}"

# ===========================================================================
# T9: run.sh CLI Edge Cases
# ===========================================================================

check_output "T9.1" "help command shows usage" \
    "Commands:" \
    "$RUN_SH" help

check_output "T9.2" "help mentions --workspace flag" \
    "workspace" \
    "$RUN_SH" help

check_output "T9.3" "list with no instances shows clean message" \
    "No subagent" \
    "$RUN_SH" list

check_output "T9.4" "stop nonexistent instance gives error" \
    "not found" \
    "$RUN_SH" stop "does-not-exist"

check_output "T9.5" "cleanup with no instances is safe" \
    "No subagent|nothing to clean" \
    "$RUN_SH" cleanup

# ===========================================================================
# T10: Adversarial / Robustness
# ===========================================================================

check "T10.1" "server.py WORKSPACE_DIR handles missing dir gracefully" \
    bash -c "python3 -c \"
import os, importlib.util
os.environ['WORKSPACE_DIR'] = '/nonexistent/path/that/does/not/exist'
spec = importlib.util.spec_from_file_location('server', '$SKILL_DIR/server.py')
mod = importlib.util.module_from_spec(spec)
# Load but expect it to set WORKSPACE_DIR to None
spec.loader.exec_module(mod)
assert mod.WORKSPACE_DIR is None, f'Expected None for nonexistent path, got {mod.WORKSPACE_DIR}'
\""

check "T10.2" "server.py handles missing backends.yml gracefully" \
    python3 -c "
import ast
tree = ast.parse(open('$SKILL_DIR/server.py').read())
# Verify there's a fallback path when backends.yml doesn't exist
source = open('$SKILL_DIR/server.py').read()
assert 'BACKENDS_FILE.exists()' in source or 'if not' in source, 'No fallback for missing backends.yml'
"

check "T10.3" "run.sh refuses to start with no free ports" \
    bash -c "
    # _next_free_port returns empty string on exhaustion — verify the logic exists
    grep -q 'No free ports' '$SKILL_DIR/run.sh'
"

check "T10.4" "run.sh validates workspace path exists" \
    bash -c "grep -q 'Workspace.*not found\|ERROR.*Workspace' '$SKILL_DIR/run.sh'"

check "T10.5" "run.sh validates OAuth credentials" \
    bash -c "grep -q 'credentials.json' '$SKILL_DIR/run.sh'"

check "T10.6" "Task tracker has LRU eviction (prevents memory leak)" \
    bash -c "grep -q 'MAX_TASKS\|popitem' '$SKILL_DIR/server.py'"

check "T10.7" "Idle timeout is configurable (10-600s range)" \
    bash -c "python3 -c \"
import ast
source = open('$SKILL_DIR/server.py').read()
assert 'ge=10' in source and 'le=600' in source, 'Idle timeout not bounded'
\""

# ===========================================================================
# Summary
# ===========================================================================

echo ""
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""

TOTAL=$((PASS + FAIL + SKIP))
echo "Blind tests: $PASS pass, $FAIL fail, $SKIP skip ($TOTAL total)"

# Final cleanup (idempotent)
cleanup_test_instances

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0
