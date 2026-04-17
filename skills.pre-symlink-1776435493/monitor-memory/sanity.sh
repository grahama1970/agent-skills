#!/usr/bin/env bash
# Real non-mocked sanity tests for monitor-memory.
# Hits real ArangoDB and checks real state files.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Source .env for ArangoDB credentials
[[ -f "$PROJECT_ROOT/.env" ]] && set -a && source "$PROJECT_ROOT/.env" && set +a
ARANGO_USER="${ARANGO_USER:-root}"
ARANGO_PASS="${ARANGO_PASS:-}"

PASS=0
FAIL=0
SKIP=0

check() {
    local label="$1"
    shift
    echo -n "  Check: $label ... "
    if "$@" > /dev/null 2>&1; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

skip() {
    local label="$1"
    local count="${2:-1}"
    echo "  Skip: $label ($count checks)"
    SKIP=$((SKIP + count))
}

warn_check() {
    local label="$1"
    shift
    echo -n "  Warn: $label ... "
    if "$@" > /dev/null 2>&1; then
        echo "OK"
        PASS=$((PASS + 1))
    else
        echo "WARN (non-critical)"
        SKIP=$((SKIP + 1))
    fi
}

echo "=== monitor-memory Sanity Check ==="
echo ""

# === Structure ===
echo "--- Structure ---"
check "SKILL.md exists" test -f "$SCRIPT_DIR/SKILL.md"
check "run.sh executable" test -x "$SCRIPT_DIR/run.sh"
check "monitor.py exists" test -f "$SCRIPT_DIR/monitor.py"
check "config.py exists" test -f "$SCRIPT_DIR/config.py"
check "db.py exists" test -f "$SCRIPT_DIR/db.py"
check "reporter.py exists" test -f "$SCRIPT_DIR/reporter.py"
check "autofix.py exists" test -f "$SCRIPT_DIR/autofix.py"
check "task_monitor_integration.py exists" test -f "$SCRIPT_DIR/task_monitor_integration.py"
check "probes/__init__.py exists" test -f "$SCRIPT_DIR/probes/__init__.py"
check "probes/tier1_data.py exists" test -f "$SCRIPT_DIR/probes/tier1_data.py"
check "probes/tier2_persona.py exists" test -f "$SCRIPT_DIR/probes/tier2_persona.py"
check "probes/tier3_smoke.py exists" test -f "$SCRIPT_DIR/probes/tier3_smoke.py"
check "probes/tier4_projects.py exists" test -f "$SCRIPT_DIR/probes/tier4_projects.py"
check "probes/tier5_infra.py exists" test -f "$SCRIPT_DIR/probes/tier5_infra.py"
check "pyproject.toml exists" test -f "$SCRIPT_DIR/pyproject.toml"

# === Dependencies ===
echo ""
echo "--- Dependencies ---"
check "typer importable" uv run --directory "$SCRIPT_DIR" python -c "import typer"
check "python-arango importable" uv run --directory "$SCRIPT_DIR" python -c "from arango import ArangoClient"
check "rich importable" uv run --directory "$SCRIPT_DIR" python -c "import rich"
check "loguru importable" uv run --directory "$SCRIPT_DIR" python -c "from loguru import logger"
check "httpx importable" uv run --directory "$SCRIPT_DIR" python -c "import httpx"

# === CLI loads ===
echo ""
echo "--- CLI ---"
check "help works" "$SCRIPT_DIR/run.sh" help
check "monitor.py --help works" uv run --directory "$SCRIPT_DIR" python monitor.py --help

# === ArangoDB connectivity (REAL) ===
echo ""
echo "--- ArangoDB ---"
if curl -sf -u "$ARANGO_USER:$ARANGO_PASS" http://127.0.0.1:8529/_api/version > /dev/null 2>&1; then
    check "ArangoDB reachable" curl -sf -u "$ARANGO_USER:$ARANGO_PASS" http://127.0.0.1:8529/_api/version

    check "required collections exist (auto-provision)" uv run --directory "$SCRIPT_DIR" python -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR'); sys.path.insert(0, '$PROJECT_ROOT/.pi/skills/memory')
from db import get_db, ensure_collections
db = get_db(); created = ensure_collections(db)
if created: print(f'  Provisioned: {created}')
# Verify the key ones exist
for c in ['lessons', 'persona_journals', 'lesson_edges', 'taxonomy_bridges', 'taxonomy_edges', 'personas']:
    assert db.has_collection(c), f'Missing: {c}'
"

    # Verify lesson_embeddings collection exists (P01 depends on it)
    check "lesson_embeddings collection exists" uv run --directory "$SCRIPT_DIR" python -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR'); sys.path.insert(0, '$PROJECT_ROOT/.pi/skills/memory')
from db import get_db; db = get_db()
assert db.has_collection('lesson_embeddings'), 'Missing: lesson_embeddings'
"

    # Real probe execution (Tier 1 only -- fast)
    check "P01 embedding-coverage runs" "$SCRIPT_DIR/run.sh" check --probe embedding-coverage --json
    check "P02 taxonomy-coverage runs" "$SCRIPT_DIR/run.sh" check --probe taxonomy-coverage --json
    check "P10 backup-freshness runs" "$SCRIPT_DIR/run.sh" check --probe backup-freshness --json
    check "P28 universal-embedding-coverage runs" "$SCRIPT_DIR/run.sh" check --probe universal-embedding-coverage --json
else
    skip "ArangoDB not reachable" 5
fi

# === State directories ===
echo ""
echo "--- State ---"
check "state dir writable" bash -c "mkdir -p ~/.pi/monitor-memory && test -w ~/.pi/monitor-memory"

# === Cross-skill dependencies ===
echo ""
echo "--- Cross-skill Dependencies ---"
check "ops-arango available" test -f "$PROJECT_ROOT/.pi/skills/ops-arango/run.sh"
warn_check "taxonomy available" test -f "$PROJECT_ROOT/.pi/skills/taxonomy/taxonomy.py"
warn_check "persona-journal available" test -f "$PROJECT_ROOT/.pi/skills/persona-journal/run.sh"
warn_check "scheduler available" test -f "$PROJECT_ROOT/.pi/skills/scheduler/run.sh"
warn_check "agent-inbox available" test -f "$PROJECT_ROOT/.pi/skills/agent-inbox/run.sh"
warn_check "embedding service health" curl -sf http://localhost:8080/health
warn_check "edge-verifier available" test -f "$PROJECT_ROOT/.pi/skills/edge-verifier/run.sh"
warn_check "12TB mounted" test -d /mnt/storage12tb

# === Registered projects (REAL) ===
echo ""
echo "--- Registered Projects ---"
if [[ -f ~/.agent_skills_targets ]]; then
    check "targets file readable" test -r ~/.agent_skills_targets
    PROJECT_COUNT=$(wc -l < ~/.agent_skills_targets)
    check "at least 1 registered project" test "$PROJECT_COUNT" -gt 0
else
    skip "no ~/.agent_skills_targets" 2
fi

# === Summary ===
echo ""
echo "================================="
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
echo "================================="
[[ $FAIL -eq 0 ]]
