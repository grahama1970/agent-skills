#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/book-extraction-verifier/.venv}"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "$HOME/.local/bin/uv" ]]; then
  UV_BIN="$HOME/.local/bin/uv"
elif [[ -x /home/graham/.local/bin/uv ]]; then
  UV_BIN=/home/graham/.local/bin/uv
elif [[ -x /usr/local/bin/uv ]]; then
  UV_BIN=/usr/local/bin/uv
else
  echo "book-extraction-verifier: uv not found in PATH, $HOME/.local/bin, /home/graham/.local/bin, or /usr/local/bin" >&2
  exit 127
fi

exec "$UV_BIN" run --project "$SCRIPT_DIR" python -m book_extraction_verifier.cli "$@"
