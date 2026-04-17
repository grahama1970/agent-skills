#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


cd "$(dirname "$0")"

case "${1:-help}" in
  heuristic)    shift; uv run python scripts/validate.py heuristic "$@" ;;
  validate)     shift; uv run python scripts/validate.py validate "$@" ;;
  validate-loop) shift; uv run python scripts/validate.py validate-loop "$@" ;;
  status)       shift; uv run python scripts/validate.py status "$@" ;;
  export-disagreements) shift; uv run python scripts/validate.py export-disagreements "$@" ;;
  retrain)
    echo "Triggering retraining via /create-gpt..."
    cd ../create-gpt
    ./run.sh iterate --task qra-assessor --max-iterations 5 --quality-threshold 0.85
    ;;
  help|*)
    echo "Usage: ./run.sh {heuristic|validate|validate-loop|status|export-disagreements|retrain}"
    echo ""
    echo "Commands:"
    echo "  heuristic           Tier 0 only (no model needed)"
    echo "  validate            Tier 0 + GPT + SciLLM fallback"
    echo "  validate-loop       Full teacher-student loop (recommended)"
    echo "  status              Show agreement tracking"
    echo "  export-disagreements Export for retraining"
    echo "  retrain             Trigger /create-gpt iterate"
    ;;
esac
