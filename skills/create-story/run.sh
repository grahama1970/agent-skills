#!/usr/bin/env bash
#
# create-story Skill Runner
# Creative writing orchestrator for Horus persona
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: ./run.sh <command> [options]

Commands:
  create <thought>              Full orchestrated workflow
  research <topic>              Research phase only
  draft --research FILE         Write draft from research
  critique <story-file>         Critique existing story
  refine <story> <critique>     Refine based on critique

Options:
  --format FORMAT               Story format (story|screenplay|podcast|novella|flash)
  --external-critique           Use external LLM for critique
  --iterations N                Number of draft iterations (default: 2)
  --output DIR                  Output directory (default: ./output)
  --help                        Show this help message

Example:
  ./run.sh create "A story about a robot discovering emotions"
  ./run.sh create "A noir screenplay" --format screenplay --external-critique
  ./run.sh research "themes of isolation in science fiction"
EOF
}

# Check for orchestrator
if [[ ! -f "${SCRIPT_DIR}/orchestrator.py" ]]; then
    echo "[create-story] Orchestrator not yet implemented."
    echo "[create-story] See 0N_TASKS.md for implementation plan."
    echo ""
    usage
    exit 1
fi

# Parse command
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    create|research|draft|critique|refine)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" "$COMMAND" "$@"
        ;;
    help|--help|-h)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
