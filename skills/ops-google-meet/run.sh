#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/ops-google-meet/venv"
exec uv run --project "$ROOT" python "$ROOT/meet.py" "$@"
