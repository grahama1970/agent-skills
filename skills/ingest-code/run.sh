#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# ingest-code skill runner
# Scans codebases for CWE mappings and stores in /memory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/ingest-code-runner-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/ingest-code-runner-pycache}"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
PYTHON="${PYTHON:-python3}"

# Check for uv
if command -v uv &>/dev/null; then
    # Don't cd - preserve user's working directory so paths like "." resolve correctly
    exec uv run --no-project --isolated \
        --with typer \
        --with httpx \
        --with loguru \
        --with python-dotenv \
        python "$SCRIPT_DIR/ingest_code.py" "$@"
else
    exec "$PYTHON" "$SCRIPT_DIR/ingest_code.py" "$@"
fi
