#!/usr/bin/env bash
# run.sh — Entry point for the nico-qa skill
# Usage: run.sh <command> [options]
#   Commands: audit, report, screenshot

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMAND="${1:-audit}"
shift 2>/dev/null || true

case "$COMMAND" in
  audit)
    uv run "$SKILL_DIR/nico_qa.py" audit "$@"
    ;;
  report)
    uv run "$SKILL_DIR/nico_qa.py" report "$@"
    ;;
  screenshot)
    echo "Screenshot command delegates to /surf for visual verification."
    echo "Navigate to ${EXPLORER_UI_URL:-http://localhost:3002} and capture tabs."
    echo ""
    echo "Use the following /surf commands:"
    echo "  surf navigate ${EXPLORER_UI_URL:-http://localhost:3002}"
    echo "  surf screenshot"
    echo ""
    echo "This command is a placeholder — invoke /surf directly from your agent."
    ;;
  *)
    echo "Unknown command: $COMMAND"
    echo "Usage: run.sh <audit|report|screenshot> [options]"
    exit 1
    ;;
esac
