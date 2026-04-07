#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# create-movie Skill Runner
# Orchestrated movie creation for Horus persona
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find project root via .env file (no brittle parent counting)
if command -v python3 &>/dev/null; then
    PROJECT_ROOT="$(python3 -c "
from pathlib import Path
p = Path('$SCRIPT_DIR')
for parent in [p] + list(p.parents):
    if (parent / '.env').exists():
        print(parent)
        break
" 2>/dev/null || echo "")"
else
    PROJECT_ROOT=""
fi

# Set memory skill path if found
if [[ -n "$PROJECT_ROOT" && -d "$PROJECT_ROOT/.agent/skills/memory" ]]; then
    export MEMORY_SKILL_PATH="$PROJECT_ROOT/.agent/skills/memory"
elif [[ -n "$PROJECT_ROOT" && -d "$PROJECT_ROOT/.pi/skills/memory" ]]; then
    export MEMORY_SKILL_PATH="$PROJECT_ROOT/.pi/skills/memory"
fi

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
    create|research|script|build-tools|generate|assemble|learn|dream)
        # Add memory project to PYTHONPATH if it exists (check env var, then relative path)
        MEMORY_SRC="${MEMORY_PROJECT_PATH:-$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")/memory}/src"
        if [[ -d "$MEMORY_SRC" ]]; then
            export PYTHONPATH="${MEMORY_SRC}:${PYTHONPATH:-}"
        fi
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" "$COMMAND" "$@"
        ;;
    sanity-full)
        exec uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sanity_full_pipeline.py" "$@"
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
