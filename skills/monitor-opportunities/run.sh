#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Local untracked environment (e.g. BUZZ_IDENTITY_KEY) for cron runs whose
# daemon env is empty; safe no-op when absent.
if [ -f "${SCRIPT_DIR}/local/env" ]; then
  # shellcheck disable=SC1091
  . "${SCRIPT_DIR}/local/env"
fi
exec uv run --project "$SCRIPT_DIR" monitor-opportunities "$@"
