#!/bin/bash
# Memory First - Query memory BEFORE scanning any codebase
#
# THE PATTERN (non-negotiable):
#   1. ./run.sh recall --q "problem"   → Check memory first (returns context)
#   2. If found=true  → Apply solution, DO NOT scan codebase
#   3. If found=false → Review context, scan codebase, then:
#      ./run.sh learn --problem "..." --solution "..."
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
JSON_HELPER="${SCRIPT_DIR}/../json_utils.py"
ORIG_ARGS=("$@")

# 0. Help (Fast response)
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Memory Agent CLI"
    echo "----------------"
    echo "Usage:"
    echo "  Recall: ./run.sh recall --q \"query string\""
    echo "  Learn:  ./run.sh learn --problem \"...\" --solution \"...\""
    echo ""
    echo "Mode:"
    if [[ -n "$MEMORY_SERVICE_URL" ]]; then
        echo "  ⚡ FAST MODE (Service): Active at $MEMORY_SERVICE_URL"
    else
        echo "  🐢 SLOW MODE (CLI): Service not set (10s startup)"
    fi
    echo ""
    echo "Parameters:"
    echo "  --q <str>      Query string for recall (NOT --query)"
    exit 0
fi

# 1. FAST PATH: Use Memory Service if available (bypasses 10s Python startup)
if [[ -n "$MEMORY_SERVICE_URL" ]]; then
    CMD="${ORIG_ARGS[0]}"
    if [[ "$CMD" == "recall" ]]; then
        set -- "${ORIG_ARGS[@]:1}"
        QUERY=""
        SCOPE=""
        K=5
        THRESHOLD=0.3
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --q) QUERY="$2"; shift 2 ;;
                --scope) SCOPE="$2"; shift 2 ;;
                --k|-k) K="$2"; shift 2 ;;
                --threshold) THRESHOLD="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        if [[ -n "$QUERY" ]]; then
            PAYLOAD="$("$JSON_HELPER" recall "$QUERY" "$SCOPE" "$K" "$THRESHOLD")"
            curl -s -X POST "$MEMORY_SERVICE_URL/recall" \
                -H "Content-Type: application/json" \
                -d "$PAYLOAD"
            exit 0
        fi
    elif [[ "$CMD" == "learn" ]]; then
        set -- "${ORIG_ARGS[@]:1}"
        PROBLEM=""
        SOLUTION=""
        SCOPE=""
        TAGS=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --problem|-p) PROBLEM="$2"; shift 2 ;;
                --solution|-s) SOLUTION="$2"; shift 2 ;;
                --scope) SCOPE="$2"; shift 2 ;;
                --tag|-t) TAGS="${TAGS:+$TAGS,}$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        if [[ -n "$PROBLEM" && -n "$SOLUTION" ]]; then
            PAYLOAD="$("$JSON_HELPER" learn "$PROBLEM" "$SOLUTION" "$SCOPE" "$TAGS")"
            curl -s -X POST "$MEMORY_SERVICE_URL/learn" \
                -H "Content-Type: application/json" \
                -d "$PAYLOAD"
            exit 0
        fi
    elif [[ "$CMD" == "health" ]]; then
        curl -s "$MEMORY_SERVICE_URL/health"
        exit 0
    fi
fi

set -- "${ORIG_ARGS[@]}"

# 2. SLOW PATH: Python CLI (Development or Global)
# Git source for graph-memory
REPO="git+https://github.com/grahama1970/graph-memory.git"

if [[ -f "$PROJECT_ROOT/pyproject.toml" ]] && grep -q 'name = "graph-memory"' "$PROJECT_ROOT/pyproject.toml" 2>/dev/null; then
    cd "$PROJECT_ROOT"
    export PYTHONPATH="src:${PYTHONPATH:-}"
    python -m graph_memory.agent_cli "$@"
elif command -v memory-agent &> /dev/null; then
    memory-agent "$@"
elif command -v uv &> /dev/null; then
    uv run --from "$REPO" memory-agent "$@"
else
    echo "Error: Neither a local install nor memory-agent binary is available." >&2
    echo "Install once with: uv pip install -e .  (or add memory-agent to PATH)" >&2
    exit 1
fi
