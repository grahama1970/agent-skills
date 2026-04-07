#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

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
CMD="${1:-}"; shift || true

usage() {
  cat <<EOF
Usage:
  ./run.sh create "<prompt>" [--variants N] [--out DIR]
  ./run.sh simulate --url URL --persona NAME --out DIR
  ./run.sh iterate --dir DIR
  ./run.sh loop "<prompt>" --persona NAME [--variants N]
EOF
}

case "$CMD" in
  create)
    node "$SKILL_DIR/scripts/create.mjs" "$@"
    ;;
  simulate)
    python3 "$SKILL_DIR/scripts/simulate_user.py" "$@"
    ;;
  iterate)
    node "$SKILL_DIR/scripts/iterate.mjs" "$@"
    ;;
  loop)
    bash "$SKILL_DIR/scripts/loop.sh" "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
