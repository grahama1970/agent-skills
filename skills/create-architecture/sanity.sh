#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV
skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${CREATE_ARCHITECTURE_UV_ENV:-/mnt/storage12tb/skills/create-architecture/.venv}"
export PYTHONDONTWRITEBYTECODE=1
exec uv run --project "$skill_dir" python "$skill_dir/scripts/eval_hub.py" --mode "${1:-smoke}"
