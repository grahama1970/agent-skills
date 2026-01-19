#!/usr/bin/env bash
# Arxiv-Learn Skill - End-to-end paper-to-memory pipeline
#
# Usage:
#   ./run.sh 2601.08058 --scope memory --context "agent systems"
#   ./run.sh --search "intent-aware memory" --scope memory
#   ./run.sh --file paper.pdf --scope research

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
PI_ROOT="${PI_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

# Load environment
[[ -f "$PI_ROOT/.env" ]] && { set -a; source "$PI_ROOT/.env"; set +a; }

# Set Python path to include skills and memory project
export PYTHONPATH="${SKILLS_DIR}:${MEMORY_ROOT:-/home/graham/workspace/experiments/memory}/src:${PYTHONPATH:-}"

# Run the pipeline
exec python3 "${SCRIPT_DIR}/arxiv_learn.py" "$@"
