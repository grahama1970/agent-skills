#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if command -v uv >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
  exec uv run python review_readme.py "$@"
fi
exec python3 review_readme.py "$@"
