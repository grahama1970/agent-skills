#!/bin/bash
# pipeline-self-repair: replayable failure -> triage -> memory/GitHub search -> ticket/watchdog handoff.
set -euo pipefail
unset VIRTUAL_ENV
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/pipeline-self-repair-uv-env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/pipeline_self_repair.py" "$@"
