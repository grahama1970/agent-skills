#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

# distill: Compatibility shim — forwards to /doc2qra
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

DOC2QRA_RUN="${SKILLS_DIR}/doc2qra/run.sh"

if [[ ! -f "${DOC2QRA_RUN}" ]]; then
    echo "[distill] ERROR: doc2qra skill not found at ${DOC2QRA_RUN}" >&2
    exit 1
fi

# Forward all arguments to doc2qra
# Legacy callers use: distill --file <path> --scope <scope>
# doc2qra expects:    distill --file <path> --scope <scope>
# The CLI interface is the same — just forward.
exec bash "$DOC2QRA_RUN" "$@"
