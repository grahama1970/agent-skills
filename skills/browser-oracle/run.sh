#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALLER_PWD="$(pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "browser-oracle: uv is required" >&2
  exit 1
fi

(
  flock 9
  if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    uv venv "$SCRIPT_DIR/.venv"
  fi
  uv sync --project "$SCRIPT_DIR" >/dev/null
) 9>"$SCRIPT_DIR/.venv.lock"

# Preserve caller cwd for default --from . (do not cd into skill dir before CLI).
export BROWSER_ORACLE_CALLER_CWD="$CALLER_PWD"

exec uv run --project "$SCRIPT_DIR" python -m browser_oracle.cli "$@"
