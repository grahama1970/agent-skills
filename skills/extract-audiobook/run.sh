#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export UV_PROJECT_ENVIRONMENT="/mnt/storage12tb/skills/extract-audiobook/.venv"
export UV_LINK_MODE=copy
unset VIRTUAL_ENV

if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "$HOME/.local/bin/uv" ]]; then
  UV_BIN="$HOME/.local/bin/uv"
elif [[ -x /home/graham/.local/bin/uv ]]; then
  UV_BIN=/home/graham/.local/bin/uv
elif [[ -x /usr/local/bin/uv ]]; then
  UV_BIN=/usr/local/bin/uv
else
  echo "extract-audiobook: uv not found" >&2
  exit 127
fi

exec "$UV_BIN" run --project "$SCRIPT_DIR" python -m extract_audiobook.cli "$@"
