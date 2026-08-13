#!/usr/bin/env bash
# ingest-code skill runner.
#
# Normal execution is lock-bound and uses run-scoped mutable paths. This script
# intentionally does not source the repository-level .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="${INGEST_CODE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
RUN_BASE="${INGEST_CODE_RUN_ROOT:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/ingest-code-runs/$RUN_ID}"
mkdir -p "$RUN_BASE"/{venv,cache,pycache,tmp}

export INGEST_CODE_RUN_ID="$RUN_ID"
export INGEST_CODE_RUN_ROOT="$RUN_BASE"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$RUN_BASE/venv}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$RUN_BASE/cache/uv}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$RUN_BASE/cache}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$RUN_BASE/pycache}"
export TMPDIR="${TMPDIR:-$RUN_BASE/tmp}"
unset VIRTUAL_ENV

if ! command -v uv >/dev/null 2>&1; then
    echo '{"error":"uv is required for locked ingest-code execution","admissible":false}' >&2
    exit 127
fi

# Preserve caller working directory so relative codebase paths still resolve.
exec uv run --project "$SCRIPT_DIR" --locked python "$SCRIPT_DIR/ingest_code.py" "$@"
