#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# create-streamdeck-page skill dispatcher
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
STREAMDECK_ROOT="$HOME/workspace/streamdeck"
STREAMDECK_CLI="$STREAMDECK_ROOT/.venv/bin/streamdeck-cli"

ACTION="${1:-help}"
shift || true

case "$ACTION" in
  create)
    cd "$SKILL_DIR"
    uv run python create_page.py create "$@"
    ;;
  deploy)
    cd "$SKILL_DIR"
    uv run python create_page.py deploy "$@"
    ;;
  evaluate)
    cd "$SKILL_DIR"
    uv run python create_page.py evaluate "$@"
    ;;
  optimize)
    cd "$SKILL_DIR"
    uv run python create_page.py optimize "$@"
    ;;
  history)
    cd "$SKILL_DIR"
    uv run python create_page.py history "$@"
    ;;
  help|*)
    cat <<EOF
create-streamdeck-page skill

Usage:
  run.sh create   --context <app> --workflows "w1,w2,w3"
  run.sh create   --from-template <name>
  run.sh create   --interactive
  run.sh deploy   --template <name> --page <idx>
  run.sh evaluate --template <name> --ground-truth contexts.json
  run.sh optimize --template <name> --rounds 3
  run.sh history  --template <name>
EOF
    ;;
esac
