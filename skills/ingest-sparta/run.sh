#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# /ingest-sparta — Thin wrapper around the real SPARTA pipeline
#
# The real pipeline lives at ~/workspace/experiments/sparta (79K LOC Python).
# This skill is an INTERFACE, not a reimplementation.
#
# Usage:
#   ./run.sh step 03 --run-id myrun --limit 100   # Run a specific pipeline step
#   ./run.sh steps                                  # List all pipeline steps
#   ./run.sh status                                 # Pipeline + data health
#   ./run.sh test                                   # Run pipeline tests
#   ./run.sh explorer                               # Launch SPARTA Explorer UX
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate the real SPARTA project
DEFAULT_ROOT="$(cd "$SCRIPT_DIR/../../../../sparta" >/dev/null 2>&1 && pwd 2>/dev/null || true)"
SPARTA_ROOT="${SPARTA_ROOT:-${DEFAULT_ROOT:-${HOME}/workspace/experiments/sparta}}"

# Load environment
for envfile in \
    "$SPARTA_ROOT/.env" \
    "${HOME}/workspace/experiments/memory/.env" \
    "$HOME/.env"; do
    if [[ -f "$envfile" ]]; then
        set -a
        source "$envfile"
        set +a
        break
    fi
done

# Use SPARTA project's virtual environment
PYTHON="${SPARTA_ROOT}/.venv/bin/python"

if [[ ! -f "$PYTHON" ]]; then
    echo "Error: SPARTA venv not found at $SPARTA_ROOT/.venv" >&2
    echo "Install first:" >&2
    echo "  cd $SPARTA_ROOT && uv venv && uv pip install -e ." >&2
    exit 1
fi

if [[ ! -d "$SPARTA_ROOT/src/sparta/pipeline" ]]; then
    echo "Error: SPARTA pipeline not found at $SPARTA_ROOT/src/sparta/pipeline" >&2
    echo "Expected project at: $SPARTA_ROOT" >&2
    exit 1
fi

export SPARTA_ROOT
exec "$PYTHON" "$SCRIPT_DIR/ingest_sparta.py" "$@"
