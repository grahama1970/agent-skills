#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# ops-runpod skill - RunPod GPU instance management
# Usage: ./run.sh list-instances
set -e

# Use local fixed version
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"

# Load RUNPOD_API_KEY from env file if not already set
if [[ -z "${RUNPOD_API_KEY:-}" ]]; then
    ENV_FILE="${RUNPOD_ENV_FILE:-$SCRIPT_DIR/.env}"
    if [[ -f "$ENV_FILE" ]]; then
        export RUNPOD_API_KEY=$(grep -E "^RUNPOD_API_KEY=" "$ENV_FILE" | head -1 | cut -d'=' -f2-)
    fi
fi

exec uv run --project "$SCRIPT_DIR" python << 'PYTHON_SCRIPT' - "$@"
import sys
sys.argv = ['runpod_ops'] + sys.argv[1:]
from runpod_ops_fixed.cli.main import app
app()
PYTHON_SCRIPT
