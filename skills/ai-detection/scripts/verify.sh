#!/usr/bin/env bash
set -euo pipefail
# Storage policy: keep the venv on the 12TB drive, not inside the skill folder.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ai-detection/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --project "$ROOT" --extra dev python "$ROOT/scripts/verify.py" "$@"
