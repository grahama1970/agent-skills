#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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

if command -v uv &> /dev/null; then
  EXEC=(uv run python)
else
  EXEC=(python3)
fi

if [ $# -eq 0 ]; then
  cat << 'USAGE'
Skills CI

Usage:
  ./run.sh scan [--best-practices LIST] [--root PATH] [--lint] [--lint-scope changed|all] [--per-skill] [--per-skill-dir PATH] [--notify PROJECT] [--learn] [--analytics] [--figure]
  ./run.sh autofix [--best-practices LIST] [--root PATH] [--notify PROJECT] [--learn] [--per-skill] [--per-skill-dir PATH]
  ./run.sh apply [--best-practices LIST] [--root PATH] [--branch NAME] [--worktree-base PATH] [--lint] [--lint-scope changed|all] [--per-skill] [--per-skill-dir PATH] [--notify PROJECT]

Defaults:
  --root: ${HOME}/workspace/experiments/pi-mono/.pi/skills
  --worktree-base: ${HOME}/workspace/experiments/pi-mono/.pi/.worktrees/skills-ci
  --best-practices: all best-practices-* skills
USAGE
  exit 0
fi

CMD="$1"
shift

case "$CMD" in
  scan)
    "${EXEC[@]}" "$SCRIPT_DIR/skills_ci.py" --mode scan "$@"
    ;;
  autofix)
    "${EXEC[@]}" "$SCRIPT_DIR/skills_ci.py" --mode autofix "$@"
    ;;
  apply)
    "${EXEC[@]}" "$SCRIPT_DIR/skills_ci.py" --mode apply "$@"
    ;;
  cache-audit)
    "${EXEC[@]}" "$SCRIPT_DIR/cache_audit.py" scan "$@"
    ;;
  cache-fix)
    "${EXEC[@]}" "$SCRIPT_DIR/cache_audit.py" fix "$@"
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    exit 1
    ;;
esac
