#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls.
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ops-agent-instructions/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/audit_agent_instructions.py" "$@"
