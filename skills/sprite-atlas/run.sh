#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-}"
if [[ -z "$cmd" ]]; then
  uv run --project "$SCRIPT_DIR" python -m sprite_atlas.cli --help
  exit 0
fi
shift
uv run --project "$SCRIPT_DIR" python -m sprite_atlas.cli "$cmd" "$@"
