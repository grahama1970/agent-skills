#!/usr/bin/env bash
# Blind adversarial tests for chutes-call skill.
# Tests run against the FastAPI app using TestClient (no Docker required).
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../../.." && pwd)/chutes-call"
PASS=0
FAIL=0
TOTAL=0

check() {
    local id="$1" desc="$2"
    shift 2
    TOTAL=$((TOTAL + 1))
    if "$@" &>/dev/null 2>&1; then
        echo "  PASS  [$id] $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  [$id] $desc"
        FAIL=$((FAIL + 1))
    fi
}

check_output() {
    local id="$1" desc="$2" pattern="$3"
    shift 3
    TOTAL=$((TOTAL + 1))
    local output
    output=$("$@" 2>&1) || true
    if echo "$output" | grep -qE "$pattern"; then
        echo "  PASS  [$id] $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  [$id] $desc (expected /$pattern/)"
        FAIL=$((FAIL + 1))
    fi
}

echo "================================================================"
echo "  BLIND ADVERSARIAL TESTS: chutes-call"
echo "================================================================"
echo ""

# ── T1: File Structure ──────────────────────────────────────────────
echo "── T1: File Structure ──"
check T1.1 "SKILL.md exists" test -f "${SKILL_DIR}/SKILL.md"
check T1.2 "server.py exists" test -f "${SKILL_DIR}/server.py"
check T1.3 "client.py exists" test -f "${SKILL_DIR}/client.py"
check T1.4 "Dockerfile exists" test -f "${SKILL_DIR}/Dockerfile"
check T1.5 "run.sh exists and executable" test -x "${SKILL_DIR}/run.sh"
check T1.6 "sanity.sh exists and executable" test -x "${SKILL_DIR}/sanity.sh"
check T1.7 "backends.yml exists" test -f "${SKILL_DIR}/backends.yml"
check T1.8 "requirements.txt exists" test -f "${SKILL_DIR}/requirements.txt"

echo ""
# ── T2: SKILL.md Frontmatter ────────────────────────────────────────
echo "── T2: SKILL.md Frontmatter ──"
check T2.1 "Has 10+ triggers" python3 -c "
import yaml
d = yaml.safe_load(open('${SKILL_DIR}/SKILL.md').read().split('---')[1])
assert len(d.get('triggers', [])) >= 10, f'only {len(d.get(\"triggers\", []))} triggers'
"
check T2.2 "Has provides list" python3 -c "
import yaml
d = yaml.safe_load(open('${SKILL_DIR}/SKILL.md').read().split('---')[1])
assert 'llm-completion' in d.get('provides', [])
"
check T2.3 "Has composes list" python3 -c "
import yaml
d = yaml.safe_load(open('${SKILL_DIR}/SKILL.md').read().split('---')[1])
assert 'ops-chutes' in d.get('composes', [])
"
check T2.4 "Has taxonomy" python3 -c "
import yaml
d = yaml.safe_load(open('${SKILL_DIR}/SKILL.md').read().split('---')[1])
assert 'infrastructure' in d.get('taxonomy', [])
"
check T2.5 "Name is chutes-call" python3 -c "
import yaml
d = yaml.safe_load(open('${SKILL_DIR}/SKILL.md').read().split('---')[1])
assert d['name'] == 'chutes-call'
"

echo ""
# ── T3: Python Syntax & Imports ─────────────────────────────────────
echo "── T3: Python Syntax & Imports ──"
check T3.1 "server.py valid Python" python3 -c "import ast; ast.parse(open('${SKILL_DIR}/server.py').read())"
check T3.2 "client.py valid Python" python3 -c "import ast; ast.parse(open('${SKILL_DIR}/client.py').read())"
check T3.3 "server.py uses loguru" python3 -c "
import ast
tree = ast.parse(open('${SKILL_DIR}/server.py').read())
imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
loguru = any('loguru' in (getattr(n, 'module', '') or '') for n in imports)
assert loguru, 'No loguru import'
"
check T3.4 "server.py uses httpx (not requests)" python3 -c "
content = open('${SKILL_DIR}/server.py').read()
assert 'import httpx' in content
assert 'import requests' not in content
"
check T3.5 "server.py uses pydantic BaseModel" python3 -c "
content = open('${SKILL_DIR}/server.py').read()
assert 'BaseModel' in content
"
check T3.6 "server.py < 800 lines" python3 -c "
lines = open('${SKILL_DIR}/server.py').readlines()
assert len(lines) < 800, f'{len(lines)} lines'
"
check T3.7 "client.py < 250 lines" python3 -c "
lines = open('${SKILL_DIR}/client.py').readlines()
assert len(lines) < 250, f'{len(lines)} lines'
"
check T3.8 "No import logging in server.py" python3 -c "
content = open('${SKILL_DIR}/server.py').read()
assert 'import logging' not in content
"

echo ""
# ── T4: Backend Configuration ───────────────────────────────────────
echo "── T4: Backend Configuration ──"
check T4.1 "backends.yml valid YAML" python3 -c "import yaml; yaml.safe_load(open('${SKILL_DIR}/backends.yml'))"
check T4.2 "Has chutes backend" python3 -c "
import yaml; d = yaml.safe_load(open('${SKILL_DIR}/backends.yml'))
assert 'chutes' in d['backends']
"
check T4.3 "Has openrouter backend" python3 -c "
import yaml; d = yaml.safe_load(open('${SKILL_DIR}/backends.yml'))
assert 'openrouter' in d['backends']
"
check T4.4 "Has gemini-flash backend" python3 -c "
import yaml; d = yaml.safe_load(open('${SKILL_DIR}/backends.yml'))
assert 'gemini-flash' in d['backends']
"
check T4.5 "Chutes is priority 1" python3 -c "
import yaml; d = yaml.safe_load(open('${SKILL_DIR}/backends.yml'))
assert d['backends']['chutes']['priority'] == 1
"
check T4.6 "Backends have cost fields" python3 -c "
import yaml; d = yaml.safe_load(open('${SKILL_DIR}/backends.yml'))
for k, b in d['backends'].items():
    assert 'cost_per_million_in' in b, f'{k} missing cost_per_million_in'
    assert 'cost_per_million_out' in b, f'{k} missing cost_per_million_out'
"

echo ""
# ── T5: FastAPI Endpoints (TestClient) ──────────────────────────────
echo "── T5: FastAPI Endpoints (TestClient) ──"
check T5.1 "GET /health returns 200" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    r = c.get('/health')
    assert r.status_code == 200
"
check T5.2 "Health has status=ok" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    assert c.get('/health').json()['status'] == 'ok'
"
check T5.3 "Health has backends dict" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    d = c.get('/health').json()
    assert 'backends' in d
    assert isinstance(d['backends'], dict)
"
check T5.4 "Health backends have circuit_state" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    d = c.get('/health').json()
    for k, v in d['backends'].items():
        assert 'circuit_state' in v, f'{k} missing circuit_state'
"
check T5.5 "GET /usage returns 200" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    assert c.get('/usage').status_code == 200
"
check T5.6 "Usage has requests field" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    d = c.get('/usage').json()
    assert 'requests' in d
    assert 'cost_usd' in d
    assert 'tokens_in' in d
"
check T5.7 "GET /queue returns 200" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    assert c.get('/queue').status_code == 200
"
check T5.8 "Queue has expected fields" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    d = c.get('/queue').json()
    for field in ['active_calls', 'semaphore_size', 'queue_depth', 'total_requests', 'callers']:
        assert field in d, f'missing {field}'
"
check T5.9 "DELETE /usage resets counters" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    r = c.delete('/usage')
    assert r.status_code == 200
    assert r.json()['status'] == 'reset'
    d = c.get('/usage').json()
    assert d['requests'] == 0
"
check T5.10 "Initial usage starts at zero" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    d = c.get('/usage').json()
    assert d['requests'] == 0
    assert d['errors'] == 0
"

echo ""
# ── T6: Request/Response Models ─────────────────────────────────────
echo "── T6: Request/Response Models ──"
check T6.1 "ChatRequest model importable" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import ChatRequest
r = ChatRequest(messages=[{'role': 'user', 'content': 'hi'}])
assert r.model == 'deepseek-ai/DeepSeek-V3'
assert r.tenacious == False
assert r.timeout == 60
"
check T6.2 "ChatResponse model importable" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import ChatResponse
r = ChatResponse(ok=True, content='hello')
assert r.ok == True
assert r.circuit_state == 'CLOSED'
"
check T6.3 "BatchRequest model importable" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import BatchRequest, ChatRequest
msgs = [{'role': 'user', 'content': 'hi'}]
b = BatchRequest(requests=[ChatRequest(messages=msgs)])
assert b.stream == True
assert b.concurrency == 5
"
check T6.4 "ChatRequest validates messages required" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import ChatRequest
from pydantic import ValidationError
try:
    ChatRequest()
    assert False, 'Should have raised'
except ValidationError:
    pass
"

echo ""
# ── T7: Circuit Breaker ─────────────────────────────────────────────
echo "── T7: Circuit Breaker ──"
check T7.1 "CircuitBreaker starts CLOSED" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import CircuitBreaker, CircuitState
cb = CircuitBreaker('test')
assert cb.state == CircuitState.CLOSED
"
check T7.2 "3 failures trip to OPEN" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import CircuitBreaker, CircuitState
cb = CircuitBreaker('test')
async def test():
    for _ in range(3):
        await cb.record_failure()
    assert cb.state == CircuitState.OPEN
asyncio.run(test())
"
check T7.3 "OPEN blocks requests" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import CircuitBreaker, CircuitState
cb = CircuitBreaker('test')
async def test():
    for _ in range(3):
        await cb.record_failure()
    assert not await cb.allow_request()
asyncio.run(test())
"
check T7.4 "Success resets to CLOSED" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import CircuitBreaker, CircuitState
cb = CircuitBreaker('test')
async def test():
    await cb.record_failure()
    await cb.record_failure()
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.consecutive_failures == 0
asyncio.run(test())
"

echo ""
# ── T8: JSON Cleaning ───────────────────────────────────────────────
echo "── T8: JSON Cleaning ──"
check T8.1 "Strips markdown fences" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import clean_json_string
result = clean_json_string('\`\`\`json\n{\"a\": 1}\n\`\`\`')
assert result == '{\"a\": 1}'
"
check T8.2 "Strips BOM" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import clean_json_string
result = clean_json_string('\ufeff{\"a\": 1}')
assert result == '{\"a\": 1}'
"
check T8.3 "try_parse_json handles valid JSON" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import try_parse_json
result = try_parse_json('{\"a\": 1}')
assert result == {'a': 1}
"
check T8.4 "try_parse_json handles markdown-wrapped JSON" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import try_parse_json
result = try_parse_json('\`\`\`json\n{\"a\": 1}\n\`\`\`')
assert result == {'a': 1}
"
check T8.5 "try_parse_json returns None for garbage" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import try_parse_json
assert try_parse_json('not json at all') is None
"
check T8.6 "try_parse_json attempts truncated JSON repair" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from server import try_parse_json
result = try_parse_json('{\"a\": 1, \"b\": 2')
assert result is not None
assert result.get('a') == 1
"

echo ""
# ── T9: Backend Resolution ──────────────────────────────────────────
echo "── T9: Backend Resolution ──"
check T9.1 "resolve_backend loads backends" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import load_backends, resolve_backend
asyncio.run(load_backends())
b = resolve_backend('deepseek-ai/DeepSeek-V3')
assert b is not None
"
check T9.2 "resolve_backend returns chutes for deepseek" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import load_backends, resolve_backend
asyncio.run(load_backends())
b = resolve_backend('deepseek-ai/DeepSeek-V3')
assert b.key == 'chutes', f'got {b.key}'
"
check T9.3 "get_fallback_chain excludes primary" python3 -c "
import sys, asyncio; sys.path.insert(0, '${SKILL_DIR}')
from server import load_backends, get_fallback_chain
asyncio.run(load_backends())
chain = get_fallback_chain('chutes')
keys = [b.key for b in chain]
assert 'chutes' not in keys
"

echo ""
# ── T10: Client Module ──────────────────────────────────────────────
echo "── T10: Client Module ──"
check T10.1 "ChutesCallClient importable" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from client import ChutesCallClient
"
check T10.2 "chat_sync importable" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from client import chat_sync
"
check T10.3 "batch_sync importable" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from client import batch_sync
"
check T10.4 "ChatResponse in client matches server" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from client import ChatResponse
r = ChatResponse(ok=True)
assert hasattr(r, 'content')
assert hasattr(r, 'circuit_state')
"
check T10.5 "Client has async context manager" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from client import ChutesCallClient
assert hasattr(ChutesCallClient, '__aenter__')
assert hasattr(ChutesCallClient, '__aexit__')
"

echo ""
# ── T11: Docker & run.sh ────────────────────────────────────────────
echo "── T11: Docker & run.sh ──"
check T11.1 "Dockerfile has non-root user" grep -q "USER" "${SKILL_DIR}/Dockerfile"
check T11.2 "Dockerfile exposes 8630" grep -q "EXPOSE 8630" "${SKILL_DIR}/Dockerfile"
check T11.3 "Dockerfile uses python:3.12-slim" grep -q "python:3.12-slim" "${SKILL_DIR}/Dockerfile"
check T11.4 "run.sh has start command" grep -q "cmd_start" "${SKILL_DIR}/run.sh"
check T11.5 "run.sh has stop command" grep -q "cmd_stop" "${SKILL_DIR}/run.sh"
check T11.6 "run.sh has health command" grep -q "cmd_health" "${SKILL_DIR}/run.sh"
check T11.7 "run.sh has embry.skill label" grep -q "embry.skill=chutes-call" "${SKILL_DIR}/run.sh"
check T11.8 "run.sh has embry.port label" grep -q "embry.port" "${SKILL_DIR}/run.sh"
check T11.9 "run.sh passes CHUTES_API_KEY" grep -q "CHUTES_API_KEY" "${SKILL_DIR}/run.sh"
check T11.10 "run.sh passes CHUTES_API_TOKEN" grep -q "CHUTES_API_TOKEN" "${SKILL_DIR}/run.sh"
check T11.11 "run.sh uses --network host" grep -q "\-\-network host" "${SKILL_DIR}/run.sh"
check T11.12 "run.sh uses --restart unless-stopped" grep -q "unless-stopped" "${SKILL_DIR}/run.sh"

echo ""
# ── T12: Sanity.sh ──────────────────────────────────────────────────
echo "── T12: Sanity.sh ──"
check_output T12.1 "sanity.sh passes" "0 failed" bash "${SKILL_DIR}/sanity.sh"

echo ""
echo "================================================================"
echo "  RESULTS: ${PASS}/${TOTAL} passed, ${FAIL} failed"
echo "================================================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
