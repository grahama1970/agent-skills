#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

# doc2qra: Document -> QRA pairs via LLM
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Find the actual project .env — SCRIPT_DIR is ~/.claude/skills/doc2qra,
# so PROJECT_ROOT (3 levels up) = ~/.claude, NOT the workspace.
# Search for .env in known locations:
EMBRY_ENV="${EMBRY_OS_ROOT:-/home/graham/workspace/experiments/embry-os}/.env"

if [ -f "$EMBRY_ENV" ]; then
    set -a
    source "$EMBRY_ENV"
    set +a
elif [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
if [ -f "${PWD}/.env" ] && [ "${PWD}/.env" != "$EMBRY_ENV" ] && [ "${PWD}/.env" != "$PROJECT_ROOT/.env" ]; then
    set -a
    source "${PWD}/.env"
    set +a
fi
# ─────────────────────────────────────────────────────────────────────────────
# Concurrency guard: warn if another doc2qra is already running
# Chutes allows 5-6 concurrent connections per token. Each doc2qra uses
# asyncio.Semaphore(6) internally — two processes = self-DoS.
# Suppress with CHUTES_SKIP_LOCK=1 if you know what you're doing.
# ─────────────────────────────────────────────────────────────────────────────
if [[ "${CHUTES_SKIP_LOCK:-0}" != "1" ]]; then
    RUNNING_COUNT=$(ps aux | grep -c '[_]_main__.py.*doc2qra\|[d]oc2qra.*__main__' 2>/dev/null || echo 0)
    if [[ "$RUNNING_COUNT" -gt 0 ]]; then
        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  WARNING: $RUNNING_COUNT doc2qra process(es) already running         ║" >&2
        echo "║                                                              ║" >&2
        echo "║  Chutes limit: 5-6 connections/token across ALL processes.   ║" >&2
        echo "║  Each doc2qra uses 6 internal async connections.             ║" >&2
        echo "║  Running multiple = self-DoS.                                ║" >&2
        echo "║                                                              ║" >&2
        echo "║  Running processes:                                          ║" >&2
        ps aux | grep '[d]oc2qra' | awk '{print "║    PID " $2 ": " $11 " " $12 " " $13}' >&2
        echo "║                                                              ║" >&2
        echo "║  Continuing in 5 seconds... (CHUTES_SKIP_LOCK=1 to skip)    ║" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
        sleep 5
    fi
fi

ENTRYPOINT="${SCRIPT_DIR}/__main__.py"

if [[ ! -f "${ENTRYPOINT}" ]]; then
    echo "[doc2qra] ERROR: entrypoint not found at ${ENTRYPOINT}" >&2
    exit 1
fi

# Shadow-LEGO: self-improvement status subcommand
if [[ "${1:-}" == "shadow-status" ]]; then
    PYTHON_CMD="uv run --directory ${SCRIPT_DIR} python"
    [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]] && PYTHON_CMD="${SCRIPT_DIR}/.venv/bin/python"
    exec $PYTHON_CMD -c "
import sys, json
sys.path.insert(0, '$(dirname "$SCRIPT_DIR")')
from doc2qra.qra_generator import build_qra_cascade
from common.subgraph_feedback import summarize_subgraph_feedback

cascade = build_qra_cascade()
shadow = cascade.shadow_report(task='qra-extraction', hours=${2:-24}) if cascade else {}
feedback = summarize_subgraph_feedback()
persona_fb = {k: v for k, v in feedback.items() if k.startswith('persona_gate:')}

status = {
    'shadow_agreement': shadow,
    'persona_feedback': persona_fb,
    'cascade_tiers': [{'tier': t.tier, 'name': t.name, 'shadow_mode': t.shadow_mode, 'is_teacher': t.is_teacher} for t in (cascade.tiers if cascade else [])],
}
print(json.dumps(status, indent=2))
"
    exit 0
fi

if [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
    exec "${SCRIPT_DIR}/.venv/bin/python" "${ENTRYPOINT}" "$@"
fi

exec uv run --directory "${SCRIPT_DIR}" python "${ENTRYPOINT}" "$@"
