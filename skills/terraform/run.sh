#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/terraform/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
exec uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/terraform_skill.py" "$@"
