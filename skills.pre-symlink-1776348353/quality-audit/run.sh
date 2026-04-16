#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Quality Audit Skill - Stratified sampling and statistical validation
#
# Usage:
#   ./run.sh sample --input results.jsonl --stratify framework --samples-per-stratum 5
#   ./run.sh audit --samples samples.json --threshold 0.85
#   ./run.sh report --input results.jsonl --output quality_report.md
#   ./run.sh sample-size --target-precision 0.05 --expected-accuracy 0.85

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Ensure dependencies
if [ ! -f ".venv/pyvenv.cfg" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Run the quality audit script
exec uv run python quality_audit.py "$@"
