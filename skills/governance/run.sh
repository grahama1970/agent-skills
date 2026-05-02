#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="${GOVERNANCE_ARTIFACT_ROOT:-/mnt/storage12tb/skills/governance}"
export UV_PROJECT_ENVIRONMENT="${GOVERNANCE_UV_ENV:-$ARTIFACT_ROOT/.venv}"
export PYTHONDONTWRITEBYTECODE=1
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
UV_PROJECT_ENVIRONMENT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve(strict=False))' "$UV_PROJECT_ENVIRONMENT")"
export UV_PROJECT_ENVIRONMENT
case "$UV_PROJECT_ENVIRONMENT" in
    "$PROJECT_ROOT"/*)
        if [ "${GOVERNANCE_ALLOW_UNSAFE_ARTIFACT_ROOT:-0}" != "1" ]; then
            echo "Error: GOVERNANCE_UV_ENV points inside the repository: $UV_PROJECT_ENVIRONMENT" >&2
            echo "Use /mnt/storage12tb or set GOVERNANCE_ALLOW_UNSAFE_ARTIFACT_ROOT=1 for an explicit unsafe override." >&2
            exit 2
        fi
        ;;
esac
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/governance_loop.py" "$@"
