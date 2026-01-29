#!/usr/bin/env bash
#
# create-movie Skill Runner
# Orchestrated movie creation for Horus persona
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: ./run.sh <command> [options]

Commands:
  create <prompt>              Full orchestrated workflow
  research <topic>             Phase 1: Research techniques
  script --from-research FILE  Phase 2: Generate script from research
  build-tools --script FILE    Phase 3: Build custom tools
  generate --tools DIR --script FILE  Phase 4: Generate assets
  assemble --assets DIR --output FILE Phase 5: Assemble final output

Options:
  --help                       Show this help message
  --dry-run                    Preview without executing

Example:
  ./run.sh create "A 30-second film about discovering colors"
  ./run.sh research "film noir lighting techniques"
EOF
}

# Check for orchestrator (not yet implemented)
if [[ ! -f "${SCRIPT_DIR}/orchestrator.py" ]]; then
    echo "[create-movie] Orchestrator not yet implemented."
    echo "[create-movie] See 0N_TASKS.md for implementation plan."
    echo ""
    usage
    exit 1
fi

# Parse command
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    create|research|script|build-tools|generate|assemble)
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
