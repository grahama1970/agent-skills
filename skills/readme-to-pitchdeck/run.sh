#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ $# -eq 0 ]]; then
  set -- --help
fi

# Prefer an already-provisioned interpreter. This avoids creating a project-local
# .venv on the code-only volume. Fall back to uv when dependencies are absent.
if "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import PIL, pydantic, pptx, typer, yaml
PY
then
  exec "$PYTHON_BIN" -m readme_to_pitchdeck.cli "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing Python dependencies and uv is unavailable." >&2
  echo "Install the dependencies from pyproject.toml or install uv." >&2
  exit 2
fi

if [[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]]; then
  if [[ -d /mnt/storage12tb && -w /mnt/storage12tb ]]; then
    export UV_PROJECT_ENVIRONMENT="/mnt/storage12tb/skills/readme-to-pitchdeck/.venv"
  else
    export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/readme-to-pitchdeck/venv"
  fi
fi

exec uv run --project "$SCRIPT_DIR" python -m readme_to_pitchdeck.cli "$@"
