#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

MEMORY_DIR="/home/graham/workspace/experiments/memory"
MONITOR_SCRIPT="$MEMORY_DIR/scripts/validation/monitor_sparta.py"
ECQ_SCRIPT="$MEMORY_DIR/scripts/validation/dimensions/evidence_case_quality.py"

# Activate memory venv
source "$MEMORY_DIR/.venv/bin/activate" 2>/dev/null || true

cd "$MEMORY_DIR"

# Route corpus-quality to the evidence case quality dimension
if [[ "${1:-}" == "corpus-quality" ]]; then
    shift
    exec python "$ECQ_SCRIPT" "$@"
fi

exec python "$MONITOR_SCRIPT" "$@"
