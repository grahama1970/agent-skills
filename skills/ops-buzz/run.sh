#!/usr/bin/env bash
set -euo pipefail

unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

if [[ -z "${BUZZ_PRIVATE_KEY:-}" && -n "${BUZZ_IDENTITY_KEY:-}" ]]; then
  export BUZZ_PRIVATE_KEY="$BUZZ_IDENTITY_KEY"
fi

cd "$SCRIPT_DIR"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/ops-buzz/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --project "$SCRIPT_DIR" python -m ops_buzz.cli "$@"
