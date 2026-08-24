#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Unified entry point for ops-qdrant skill (read-only Qdrant health).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Load repo-root .env if present (QDRANT_URL, MEMORY_URL, EMBED_URL overrides)
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/ops_qdrant.py" "$@"
