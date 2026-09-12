#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${UV_PROJECT_ENVIRONMENT:-}" || "${UV_PROJECT_ENVIRONMENT:-}" == "$SCRIPT_DIR/.venv" || "${UV_PROJECT_ENVIRONMENT:-}" == "skills/acceptance-contract/.venv" ]]; then
  export UV_PROJECT_ENVIRONMENT="/mnt/storage12tb/skills/acceptance-contract/.venv"
fi
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
exec uv run --project "$SCRIPT_DIR" python -m acceptance_contract.cli "$@"
