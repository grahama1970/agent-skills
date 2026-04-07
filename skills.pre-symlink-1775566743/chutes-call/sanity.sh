#!/usr/bin/env bash
# sanity.sh — chutes-call prerequisite checks
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" &>/dev/null; then
        echo "  PASS  $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== chutes-call sanity checks ==="

# Required files
for f in SKILL.md server.py client.py Dockerfile run.sh backends.yml requirements.txt; do
    check "File exists: $f" test -f "${SKILL_DIR}/$f"
done

# Python syntax
check "server.py syntax valid" python3 -c "import ast; ast.parse(open('${SKILL_DIR}/server.py').read())"
check "client.py syntax valid" python3 -c "import ast; ast.parse(open('${SKILL_DIR}/client.py').read())"

# YAML valid
check "backends.yml valid YAML" python3 -c "import yaml; yaml.safe_load(open('${SKILL_DIR}/backends.yml'))"

# SKILL.md has triggers
check "SKILL.md has triggers" python3 -c "
import yaml
d = yaml.safe_load(open('${SKILL_DIR}/SKILL.md').read().split('---')[1])
assert len(d.get('triggers', [])) >= 5
"

# Dependencies importable
check "fastapi importable" python3 -c "import fastapi"
check "httpx importable" python3 -c "import httpx"
check "tenacity importable" python3 -c "import tenacity"
check "loguru importable" python3 -c "from loguru import logger"
check "pydantic importable" python3 -c "from pydantic import BaseModel"

# Docker available
check "Docker available" docker --version

# API key exists
check "Chutes API key in env" python3 -c "
import os
assert os.getenv('CHUTES_API_TOKEN') or os.getenv('CHUTES_API_KEY'), 'No Chutes key'
"

# FastAPI app loads and health endpoint works
check "FastAPI app loads with health" python3 -c "
import sys; sys.path.insert(0, '${SKILL_DIR}')
from fastapi.testclient import TestClient
from server import app
with TestClient(app) as c:
    r = c.get('/health')
    assert r.status_code == 200
"

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
