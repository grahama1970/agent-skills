#!/bin/bash
# Memory First - Query memory BEFORE scanning any codebase
#
# THE PATTERN (non-negotiable):
#   1. ./run.sh recall --q "problem"   → Check memory first (returns context)
#   2. If found=true  → Apply solution, DO NOT scan codebase
#   3. If found=false → Review context, scan codebase, then:
#      ./run.sh learn --problem "..." --solution "..."
#
# TWO COMMANDS (all you need):
#   ./run.sh recall --q "ImportError when running tests"
#   ./run.sh learn --problem "..." --solution "..."

set -e

# Git source for graph-memory
REPO="git+https://github.com/grahama1970/graph-memory.git"

# Check if we're in the local memory project (development mode)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

if [[ -f "$PROJECT_ROOT/pyproject.toml" ]] && grep -q 'name = "graph-memory"' "$PROJECT_ROOT/pyproject.toml" 2>/dev/null; then
    # Development mode - use local installation
    cd "$PROJECT_ROOT"
    PYTHONPATH=src uv run python -m graph_memory.agent_cli "$@"
elif command -v uv &> /dev/null; then
    # Production mode - install from git
    uv run --from "$REPO" memory-agent "$@"
elif command -v memory-agent &> /dev/null; then
    # Fallback to global installation
    memory-agent "$@"
else
    echo "Error: Neither uv nor memory-agent found" >&2
    echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi
