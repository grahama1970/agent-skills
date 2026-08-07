#!/bin/bash
# monitor-projects entrypoint. All Python goes through uv for dependency isolation.
unset VIRTUAL_ENV
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/monitor_projects.py" "$@"
