#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install package in editable mode if not already
if [[ ! -f "$SKILL_DIR/.venv/.installed" ]]; then
    uv pip install --project "$SKILL_DIR" -e "$SKILL_DIR" 2>/dev/null || true
    touch "$SKILL_DIR/.venv/.installed"
fi

CMD="${1:-recommend}"
shift || true

case "$CMD" in
  recommend|evaluate|chains|shadow-status|train|status)
    uv run --project "$SKILL_DIR" python -m src.cli "$CMD" "$@"
    ;;
  *)
    echo "Usage: ./run.sh {recommend|evaluate|chains|shadow-status|train|status} [options]"
    echo ""
    echo "Commands:"
    echo "  recommend      Recommend skill chains for a task"
    echo "  evaluate       Evaluate a specific skill pair/chain"
    echo "  chains         List known chains from training data"
    echo "  shadow-status  Show shadow-LEGO agreement rate"
    echo "  train          Retrain from accumulated labels"
    echo "  status         Health check"
    exit 1
    ;;
esac
